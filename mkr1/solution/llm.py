"""Клієнт локальних моделей Ollama (чат і embeddings) та тестовий mock-режим.

Налаштування через змінні середовища:
  LLM_BACKEND     ollama (за замовчуванням) або mock
  OLLAMA_URL      http://localhost:11434
  OLLAMA_MODEL    qwen2.5:7b-instruct   (відповіді)
  EMBED_MODEL     bge-m3                (пошук по фрагментах)
  EMBED_ON_CPU    1                     (embeddings на CPU, щоб не займати відеопам'ять; 0 = на GPU)
  OLLAMA_NUM_CTX  4096                  (контекст чату)
  OLLAMA_NUM_PREDICT 512                (максимум токенів відповіді)
  OLLAMA_KEEP_ALIVE 30m                 (як довго тримати моделі в пам'яті після запиту)
  EMBED_WORKERS   2                     (скільки пачок фрагментів рахувати паралельно під час індексації)
  EMBED_INDEX_ON_GPU 0                  (1 = індексацію рахувати на GPU, питання лишаються на CPU; швидше, але потрібна пам'ять)
  OLLAMA_TIMEOUT  300                   (секунд на запит)
"""
import json
import os
import re
import zlib

import requests


class LLMError(Exception):
    """Помилка, після якої можна спробувати ще раз."""


class LLMUnavailable(LLMError):
    """Ollama або модель недоступні: повторювати немає сенсу."""


def _settings() -> dict:
    return {
        "backend": os.getenv("LLM_BACKEND", "ollama").lower(),
        "url": os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        "embed_model": os.getenv("EMBED_MODEL", "bge-m3"),
        "embed_cpu": os.getenv("EMBED_ON_CPU", "1") == "1",
        "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
        "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "512")),
        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
        "embed_workers": max(1, int(os.getenv("EMBED_WORKERS", "2"))),
        "index_gpu": os.getenv("EMBED_INDEX_ON_GPU", "0") == "1",
        "timeout": float(os.getenv("OLLAMA_TIMEOUT", "300")),
    }


def parse_json(content: str):
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return json.loads(content)


def _post(cfg: dict, path: str, payload: dict) -> requests.Response:
    try:
        return requests.post(f"{cfg['url']}{path}", json=payload, timeout=cfg["timeout"])
    except requests.ConnectionError as error:
        raise LLMUnavailable(f"Ollama не відповідає за адресою {cfg['url']}. Запустіть Ollama.") from error
    except requests.Timeout as error:
        raise LLMError("модель не відповіла вчасно") from error


def chat_json(system: str, user: str, schema: dict, *, task: str, context: dict | None = None, temperature: float = 0.1) -> dict:
    """Один запит до моделі. task і context потрібні лише mock-режиму."""
    cfg = _settings()
    if cfg["backend"] == "mock":
        return _mock_chat(task, context or {})
    if cfg["backend"] != "ollama":
        raise ValueError(f"Невідомий LLM_BACKEND: {cfg['backend']}")

    payload = {
        "model": cfg["model"],
        "stream": False,
        "format": schema,
        "keep_alive": cfg["keep_alive"],
        "options": {"temperature": temperature, "num_ctx": cfg["num_ctx"], "num_predict": cfg["num_predict"]},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    last_problem = "порожня відповідь"
    for _ in range(3):
        response = _post(cfg, "/api/chat", payload)
        if response.status_code == 404:
            raise LLMUnavailable(f"Модель {cfg['model']} не знайдено. Виконайте: ollama pull {cfg['model']}")
        if response.status_code == 400 and payload["format"] != "json":
            payload["format"] = "json"
            continue
        if not response.ok:
            raise LLMError(f"Ollama повернула помилку {response.status_code}")
        try:
            data = parse_json(response.json()["message"]["content"])
        except (ValueError, KeyError) as error:
            last_problem = f"некоректний JSON ({error})"
            continue
        if isinstance(data, dict):
            return data
        last_problem = "очікувався JSON-об'єкт"
    raise LLMError(last_problem)


class AnswerStreamer:
    """Дістає значення поля "answer" з JSON, який надходить шматками, щоб показувати текст одразу."""

    _START = re.compile(r'"answer"\s*:\s*"')
    _ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/"}

    def __init__(self):
        self.buffer = ""
        self.sent = 0

    def feed(self, piece: str) -> str:
        """Додає шматок JSON і повертає новий фрагмент тексту відповіді (або порожній рядок)."""
        self.buffer += piece
        start = self._START.search(self.buffer)
        if not start:
            return ""
        text, i, out = self.buffer, start.end(), []
        while i < len(text):
            ch = text[i]
            if ch == '"':
                break
            if ch == "\\":
                if i + 1 >= len(text):
                    break
                nxt = text[i + 1]
                if nxt == "u":
                    code = text[i + 2:i + 6]
                    if len(code) < 4:
                        break
                    try:
                        out.append(chr(int(code, 16)))
                    except ValueError:
                        break
                    i += 6
                    continue
                out.append(self._ESCAPES.get(nxt, nxt))
                i += 2
                continue
            out.append(ch)
            i += 1
        full = "".join(out)
        delta, self.sent = full[self.sent:], len(full)
        return delta


def chat_stream(system: str, user: str, schema: dict, *, task: str, context: dict | None = None, temperature: float = 0.1):
    """Генератор для відповіді «по слову»: ("delta", текст) під час генерації і наприкінці ("done", dict)."""
    cfg = _settings()
    if cfg["backend"] == "mock":
        data = _mock_chat(task, context or {})
        for word in re.findall(r"\S+\s*", data["answer"]):
            yield "delta", word
        yield "done", data
        return
    if cfg["backend"] != "ollama":
        raise ValueError(f"Невідомий LLM_BACKEND: {cfg['backend']}")

    payload = {
        "model": cfg["model"], "stream": True, "format": schema, "keep_alive": cfg["keep_alive"],
        "options": {"temperature": temperature, "num_ctx": cfg["num_ctx"], "num_predict": cfg["num_predict"]},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    last_problem, emitted = "порожня відповідь", False
    for _ in range(2):
        try:
            response = requests.post(f"{cfg['url']}/api/chat", json=payload, timeout=cfg["timeout"], stream=True)
        except requests.ConnectionError as error:
            raise LLMUnavailable(f"Ollama не відповідає за адресою {cfg['url']}. Запустіть Ollama.") from error
        except requests.Timeout as error:
            raise LLMError("модель не відповіла вчасно") from error
        try:
            if response.status_code == 404:
                raise LLMUnavailable(f"Модель {cfg['model']} не знайдено. Виконайте: ollama pull {cfg['model']}")
            if response.status_code == 400 and payload["format"] != "json":
                payload["format"] = "json"
                continue
            if not response.ok:
                raise LLMError(f"Ollama повернула помилку {response.status_code}")
            streamer = AnswerStreamer()
            try:
                for line in response.iter_lines():
                    if not line:
                        continue
                    piece = json.loads(line).get("message", {}).get("content", "")
                    delta = streamer.feed(piece) if piece else ""
                    if delta:
                        emitted = True
                        yield "delta", delta
            except requests.RequestException as error:
                raise LLMError("з'єднання з моделлю перервано") from error
            try:
                data = parse_json(streamer.buffer)
            except ValueError as error:
                last_problem = f"некоректний JSON ({error})"
                if emitted:
                    break
                continue
            if isinstance(data, dict):
                yield "done", data
                return
            last_problem = "очікувався JSON-об'єкт"
        finally:
            response.close()
    raise LLMError(last_problem)


def warmup() -> None:
    """Завантажує обидві моделі в пам'ять заздалегідь, щоб перше питання не чекало на завантаження."""
    cfg = _settings()
    if cfg["backend"] != "ollama":
        return
    try:
        requests.post(f"{cfg['url']}/api/chat", json={"model": cfg["model"], "messages": [], "keep_alive": cfg["keep_alive"]}, timeout=cfg["timeout"])
        payload = {"model": cfg["embed_model"], "input": "привіт", "keep_alive": cfg["keep_alive"]}
        if cfg["embed_cpu"]:
            payload["options"] = {"num_gpu": 0}
        requests.post(f"{cfg['url']}/api/embed", json=payload, timeout=cfg["timeout"])
    except requests.RequestException:
        pass


EMBED_BATCH = 16


def embed(texts: list[str], kind: str = "query") -> list[list[float]]:
    """Повертає вектор для кожного тексту. kind="index" для індексації файлів, "query" для питань."""
    cfg = _settings()
    on_cpu = cfg["embed_cpu"] and not (kind == "index" and cfg["index_gpu"])
    if cfg["backend"] == "mock":
        return [_mock_embed(t) for t in texts]

    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        payload = {"model": cfg["embed_model"], "input": batch, "keep_alive": cfg["keep_alive"]}
        if on_cpu:
            payload["options"] = {"num_gpu": 0}
        response = _post(cfg, "/api/embed", payload)
        if response.status_code == 404:
            raise LLMUnavailable(f"Модель {cfg['embed_model']} не знайдено. Виконайте: ollama pull {cfg['embed_model']}")
        if not response.ok:
            raise LLMError(f"Ollama повернула помилку {response.status_code} для embeddings")
        try:
            result = response.json()["embeddings"]
        except (ValueError, KeyError) as error:
            raise LLMError("некоректна відповідь embeddings") from error
        if len(result) != len(batch):
            raise LLMError("кількість векторів не збігається з кількістю фрагментів")
        vectors.extend(result)
    return vectors


def _stems(text: str) -> list[str]:
    return [w[:5] for w in re.findall(r"\w{4,}", text.lower())]


def _mock_embed(text: str, dim: int = 256) -> list[float]:
    vector = [0.0] * dim
    for stem in _stems(text):
        vector[zlib.crc32(stem.encode()) % dim] += 1.0
    return vector


def _mock_chat(task: str, context: dict) -> dict:
    if task != "answer":
        raise ValueError(f"Невідоме завдання mock: {task}")
    question_stems = {s for s in _stems(context.get("question", "")) if len(s) >= 5}
    best, best_overlap, best_index = "", 0, 0
    for index, fragment in enumerate(context.get("fragments", []), start=1):
        for sentence in re.split(r"(?<=[.!?])\s+", fragment):
            overlap = len(question_stems & set(_stems(sentence)))
            if overlap > best_overlap:
                best, best_overlap, best_index = sentence.strip(), overlap, index
    if best_overlap >= 2:
        return {"found": True, "quote": best, "answer": best, "sources": [best_index]}
    return {"found": False, "quote": "", "answer": "У матеріалах не знайдено відповіді.", "sources": []}


def status() -> dict:
    """Стан обох моделей для індикатора в інтерфейсі."""
    cfg = _settings()
    if cfg["backend"] == "mock":
        return {"ok": True, "backend": "mock", "model": "mock", "message": "Тестовий режим без моделей"}
    try:
        tags = requests.get(f"{cfg['url']}/api/tags", timeout=3).json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "backend": "ollama", "model": cfg["model"], "message": "Ollama не запущена"}
    names = [m.get("name", "") for m in tags.get("models", [])]
    for model in (cfg["model"], cfg["embed_model"]):
        wanted = model if ":" in model else model + ":latest"
        if wanted not in names:
            return {"ok": False, "backend": "ollama", "model": cfg["model"], "message": f"Немає моделі. Виконайте: ollama pull {model}"}
    return {"ok": True, "backend": "ollama", "model": cfg["model"], "message": f"Моделі готові (пошук: {cfg['embed_model']})"}
