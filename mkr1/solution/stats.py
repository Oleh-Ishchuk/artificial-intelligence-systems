"""Метрики використання за журналом evidence/logs/rag.jsonl.

Запуск:  python stats.py [шлях до журналу] [--baseline-min 4.0] [--out файл.md]
--baseline-min: скільки хвилин у середньому йшов пошук відповіді вручну («до»).
--out: додатково записати таблицю у файл (UTF-8).
"""
import argparse
import json
from pathlib import Path
from statistics import mean

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "evidence" / "logs" / "rag.jsonl"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compute(events: list[dict], baseline_min: float | None = None) -> dict:
    indexed = [e for e in events if e["event"] == "index"]
    asks = {e["id"]: e for e in events if e["event"] == "ask"}
    feedback = {e["id"]: e for e in events if e["event"] == "feedback"}

    m = {"files": len(indexed), "chunks": sum(e["chunks"] for e in indexed), "asks": len(asks)}
    if indexed:
        m["avg_index_s"] = mean(e["seconds"] for e in indexed)
    if asks:
        m["found_share"] = sum(bool(a["found"]) for a in asks.values()) / len(asks)
        m["avg_retrieval_s"] = mean(a["retrieval_s"] for a in asks.values())
        m["avg_llm_s"] = mean(a["llm_s"] for a in asks.values())
        m["avg_ai_s"] = m["avg_retrieval_s"] + m["avg_llm_s"]

    rated = [feedback[i] for i in asks if i in feedback]
    correct = [f["correct"] for f in rated if f.get("correct") is not None]
    source_ok = [f["source_ok"] for f in rated if f.get("source_ok") is not None]
    elapsed = [f["elapsed_s"] for f in rated if f.get("elapsed_s") is not None]
    if correct:
        m["correct_n"], m["correct_share"] = len(correct), sum(bool(c) for c in correct) / len(correct)
    if source_ok:
        m["source_n"], m["source_share"] = len(source_ok), sum(bool(c) for c in source_ok) / len(source_ok)
    if elapsed:
        m["avg_total_s"] = mean(elapsed)
        if baseline_min:
            m["baseline_s"] = baseline_min * 60
            m["saving_pct"] = 100 * (1 - m["avg_total_s"] / (baseline_min * 60))
    return m


def _pct(value) -> str:
    return "н/д" if value is None else f"{value * 100:.0f}%"


def render(m: dict) -> str:
    def num(key, fmt="{:.1f}"):
        return fmt.format(m[key]) if key in m else "н/д"

    rows = [
        ("Проіндексовано файлів / фрагментів", f"{m['files']} / {m['chunks']}"),
        ("Середній час індексації файлу, с", num("avg_index_s")),
        ("Задано питань", str(m["asks"])),
        ("Питань, на які знайдено відповідь", _pct(m.get("found_share"))),
        ("Середній час пошуку, с", num("avg_retrieval_s")),
        ("Середній час відповіді моделі, с", num("avg_llm_s")),
        ("Середній час AI на питання, с", num("avg_ai_s")),
        ("Ручний пошук «до», с", num("baseline_s", "{:.0f}")),
        ("Повний час «після» із перевіркою джерела, с", num("avg_total_s")),
        ("Економія часу", f"{m['saving_pct']:.0f}%" if "saving_pct" in m else "н/д"),
        ("Відповіді, визнані правильними", f"{_pct(m.get('correct_share'))} (з {m.get('correct_n', 0)})"),
        ("Джерело знайдено правильно", f"{_pct(m.get('source_share'))} (з {m.get('source_n', 0)})"),
    ]
    width_a = max(len(a) for a, _ in rows + [("Показник", "")])
    width_b = max(len(b) for _, b in rows + [("", "Значення")])
    line = lambda a, b: f"| {a.ljust(width_a)} | {b.rjust(width_b)} |"
    out = ["Метрики використання за журналом rag.jsonl", "", line("Показник", "Значення"), f"|{'-' * (width_a + 2)}|{'-' * (width_b + 1)}:|"]
    out += [line(a, b) for a, b in rows]
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", nargs="?", default=str(DEFAULT_LOG))
    parser.add_argument("--baseline-min", type=float, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    text = render(compute(load(Path(args.log)), args.baseline_min))
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
