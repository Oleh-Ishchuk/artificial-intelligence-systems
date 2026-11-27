"""Flask-застосунок: «Питай по моїх файлах» (RAG, локальні моделі Ollama)."""
import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

import ingest
import llm
import rag

BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE / "data"))
LOG_DIR = Path(os.getenv("LOG_DIR", BASE.parent / "evidence" / "logs"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

INDEX = rag.Index(DATA_DIR)
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def log(event: str, record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **record}
    with open(LOG_DIR / "rag.jsonl", "a", encoding="utf-8") as file:
        file.write(json.dumps(line, ensure_ascii=False) + "\n")


def _fail(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _model_names() -> dict:
    cfg = llm._settings()
    if cfg["backend"] == "mock":
        return {"model": "mock", "embed_model": "mock"}
    return {"model": cfg["model"], "embed_model": cfg["embed_model"]}


@app.get("/")
def index_page():
    return render_template("index.html", formats=", ".join(sorted(e.lstrip(".") for e in ingest.ALLOWED)))


@app.get("/api/status")
def api_status():
    return jsonify(llm.status())


@app.get("/api/docs")
def api_docs():
    return jsonify({"docs": INDEX.summaries()})


@app.delete("/api/docs/<doc_id>")
def api_delete_doc(doc_id: str):
    if not INDEX.remove(doc_id):
        return _fail("Документ не знайдено", 404)
    log("delete", {"doc_id": doc_id})
    return jsonify({"ok": True})


@app.post("/api/docs")
def api_upload():
    files = [(upload.filename, upload.read()) for upload in request.files.getlist("files") if upload.filename]
    if not files:
        return _fail("Виберіть хоча б один файл")
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "status": "running", "files_total": len(files), "files_done": 0, "results": [],
           "files": [{"name": name, "status": "queued", "done": 0, "total": 0} for name, _ in files]}
    with JOBS_LOCK:
        while len(JOBS) >= 50:
            JOBS.pop(next(iter(JOBS)))
        JOBS[job_id] = job
    threading.Thread(target=_index_worker, args=(job, files), daemon=True).start()
    return jsonify({"job_id": job_id})


def _index_worker(job: dict, files) -> None:
    for entry, (name, data) in zip(job["files"], files):
        entry["status"] = "indexing"
        try:
            result = rag.index_file(INDEX, name, data, on_progress=lambda done, total, e=entry: e.update(done=done, total=total))
            entry.update(status="skipped" if result["skipped"] else "done", doc_id=result["id"], seconds=result["seconds"])
            job["results"].append({"name": name, "status": "skipped" if result["skipped"] else "ok", **result})
            if not result["skipped"]:
                log("index", {"file": name, "chunks": result["chunks"], "pages": result["pages"], "chars": result["chars"],
                              "seconds": result["seconds"], **_model_names()})
        except (ValueError, llm.LLMError) as error:
            entry.update(status="error", error=str(error))
            job["results"].append({"name": name, "status": "error", "error": str(error)})
            if isinstance(error, llm.LLMUnavailable):
                job["files_done"] += 1
                for rest in job["files"]:
                    if rest["status"] == "queued":
                        rest.update(status="error", error=str(error))
                break
        except Exception:
            message = f"Не вдалося прочитати файл {name}"
            entry.update(status="error", error=message)
            job["results"].append({"name": name, "status": "error", "error": message})
        job["files_done"] += 1
    job["status"] = "done"


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    job = JOBS.get(job_id)
    return jsonify(job) if job else _fail("Завдання не знайдено", 404)


def _ask_params():
    """Перевіряє тіло запиту. Повертає (питання, doc_ids, None) або (None, None, відповідь-помилка)."""
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()[:1000]
    if len(question) < 3:
        return None, None, _fail("Напишіть питання")
    if not INDEX.docs:
        return None, None, _fail("Спершу завантажте документи")
    return question, [str(i) for i in data.get("doc_ids") or []] or None, None


def _log_ask(ask_id: str, question: str, result: dict, doc_ids, **extra) -> None:
    log("ask", {
        "id": ask_id, **_model_names(), "question": question, "found": result["found"], "answer": result["answer"],
        "low_confidence": result["low_confidence"], "verified": result.get("verified"), "retrieval_s": result["retrieval_s"], "llm_s": result["llm_s"],
        "docs_filter": len(doc_ids) if doc_ids else 0, **extra,
        "sources": [{"file": s["file"], "page": s["page"], "score": s["score"], "used": s["used"]} for s in result["sources"]],
    })


@app.post("/api/ask")
def api_ask():
    question, doc_ids, error = _ask_params()
    if error:
        return error
    try:
        result = rag.answer_question(INDEX, question, doc_ids=doc_ids)
    except llm.LLMUnavailable as error:
        return _fail(str(error), 503)
    except llm.LLMError as error:
        return _fail(f"Не вдалося отримати відповідь: {error}", 502)
    ask_id = uuid.uuid4().hex[:10]
    _log_ask(ask_id, question, result, doc_ids)
    return jsonify({"id": ask_id, **result})


@app.post("/api/ask/stream")
def api_ask_stream():
    """Відповідь потоком: кожен рядок це JSON-подія (retrieval, delta, done або error)."""
    question, doc_ids, error = _ask_params()
    if error:
        return error

    def events():
        try:
            for event in rag.answer_stream(INDEX, question, doc_ids=doc_ids):
                if event["type"] == "done":
                    ask_id = uuid.uuid4().hex[:10]
                    result = event["result"]
                    _log_ask(ask_id, question, result, doc_ids, first_token_s=result.get("first_token_s"), stream=True)
                    event = {"type": "done", "result": {"id": ask_id, **result}}
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except llm.LLMUnavailable as error:
            yield json.dumps({"type": "error", "error": str(error)}, ensure_ascii=False) + "\n"
        except llm.LLMError as error:
            yield json.dumps({"type": "error", "error": f"Не вдалося отримати відповідь: {error}"}, ensure_ascii=False) + "\n"

    return Response(events(), mimetype="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/feedback")
def api_feedback():
    data = request.get_json(silent=True) or {}
    log("feedback", {key: data.get(key) for key in ("id", "correct", "source_ok", "elapsed_s")})
    return jsonify({"ok": True})


if __name__ == "__main__":
    if os.getenv("WARMUP", "1") == "1":
        threading.Thread(target=llm.warmup, daemon=True).start()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
