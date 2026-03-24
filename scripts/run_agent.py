#!/usr/bin/env python3
"""
Точка входа: вопрос с stdin или аргументом, ответ в stdout.
Пример: echo "Сколько записей в consumption?" | python scripts/run_agent.py
       python scripts/run_agent.py "Сколько записей в consumption?"
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.orchestrator import run_agent


def main() -> None:
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = sys.stdin.read().strip()

    result = run_agent(question)

    if result.get("ok"):
        tools = result.get("tools_called", [])
        if tools:
            print("Вызванные инструменты:", ", ".join(tools), file=sys.stderr)
        print(result.get("answer", ""))
    else:
        print(result.get("error", "Неизвестная ошибка"), file=sys.stderr)
        if result.get("sql"):
            print(f"SQL: {result['sql'][:300]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
