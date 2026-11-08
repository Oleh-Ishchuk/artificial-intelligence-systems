"""Генератор commit-повідомлень: git diff -> повідомлення у форматі Conventional Commits.

Працює з локальною моделлю через OpenAI-сумісний API (Ollama).

Встановлення і запуск:
    1. Встановіть Ollama, Python 3.10+ і пакет:   pip install openai
    2. Завантажте модель:                         ollama pull qwen3:4b-instruct-2507-q4_K_M
    3. У git-репозиторії додайте зміни (git add ...) і запустіть:
           python commit_msg.py                   # бере git diff --staged
           python commit_msg.py --file diff.txt   # або diff із файлу
"""

import argparse
import re
import subprocess
import sys

from openai import APIConnectionError, APITimeoutError, NotFoundError, OpenAI

# Параметри генерації (обґрунтування в README.md)
TEMPERATURE = 0.2   # низька: потрібен стабільний формат, а не творчість
MAX_TOKENS = 60     # обовʼязковий ліміт; рядок до 72 символів це ~25 токенів, решта запас
MAX_DIFF_CHARS = 6000  # ~2000 токенів: разом із промптом вміщається в контекст Ollama 4096 токенів

SYSTEM_PROMPT = """Ти пишеш commit-повідомлення за git diff у форматі Conventional Commits.
Відповідай ОДНИМ рядком англійською: <type>(<scope>): <опис>. До 72 символів, без крапки в кінці, без пояснень.
Типи:
feat: нова функціональність
fix: виправлення помилки
docs: лише документація (README, коментарі)
style: лише форматування (відступи, порядок імпортів), логіка не змінюється
refactor: зміна коду без нової функції й без виправлення помилки
perf: пришвидшення роботи
test: додавання або зміна тестів
build: збірка, залежності, Dockerfile
chore: інше службове
Приклади:
Зміна: додано тести для calculate_discount -> test(discount): add unit tests for calculate_discount
Зміна: у README виправлено одруківку -> docs(readme): fix typo in run command
Зміна: змінено лише порядок імпортів -> style(utils): reorder imports
Зміна: запит переписано, працює вдвічі швидше -> perf(schedule): speed up get_schedule with a single query"""

FORMAT = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|chore|ci|revert)(\([^)]+\))?!?: \S.*$")


def parse_args():
    parser = argparse.ArgumentParser(description="Генерує commit-повідомлення за git diff.")
    parser.add_argument("--file", help="файл із diff (за замовчуванням береться git diff --staged)")
    parser.add_argument("--base-url", default="http://localhost:11434/v1", help="адреса API, разом із /v1")
    parser.add_argument("--model", default="qwen3:4b-instruct-2507-q4_K_M", help="назва моделі на сервері")
    parser.add_argument("--timeout", type=float, default=60, help="таймаут запиту, секунди")
    return parser.parse_args()


def get_diff(path):
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError as error:
            sys.exit(f"Помилка: не вдалося прочитати файл {path}: {error}")
    try:
        result = subprocess.run(["git", "diff", "--staged"], capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        sys.exit("Помилка: git не знайдено. Встановіть git або використайте --file.")
    if result.returncode != 0:
        sys.exit(f"Помилка git: {result.stderr.strip()}")
    return result.stdout


def main():
    args = parse_args()
    diff = get_diff(args.file).strip()
    if not diff:
        sys.exit("Немає змін: додайте файли командою git add або вкажіть --file.")
    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        diff = diff[:MAX_DIFF_CHARS]
        print(f"Увага: diff завеликий, взято перші {MAX_DIFF_CHARS} символів.", file=sys.stderr)

    client = OpenAI(base_url=args.base_url, api_key="local", timeout=args.timeout)
    print("Генерую повідомлення...", file=sys.stderr)
    message = ""
    try:
        stream = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": f"Diff:\n{diff}"}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                piece = chunk.choices[0].delta.content
                message += piece
                print(piece, end="", flush=True)  # відповідь друкується в міру генерації
        print()
    except APITimeoutError:
        sys.exit(f"\nПомилка: сервер не відповів за {args.timeout:.0f} с. Спробуйте ще раз або збільште --timeout.")
    except APIConnectionError:
        sys.exit("\nПомилка: не вдалося підключитися до сервера. Запустіть Ollama і перевірте --base-url.")
    except NotFoundError:
        sys.exit(f"\nПомилка: модель {args.model} не знайдена. Завантажте її: ollama pull {args.model}")

    message = message.strip()
    if not message:
        sys.exit("Помилка: модель повернула порожню відповідь. Спробуйте ще раз.")
    if truncated:
        print("Увага: повідомлення складено лише за початком diff, перевірте, чи воно описує всі зміни.", file=sys.stderr)
    if not FORMAT.match(message.splitlines()[0]):
        print("Увага: відповідь не у форматі Conventional Commits. Запустіть ще раз або відредагуйте вручну.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
