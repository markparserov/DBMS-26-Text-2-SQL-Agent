#!/usr/bin/env python3
"""
Сборка RAG-индексов: DDL+комментарии и (опционально) примеры запросов.
По умолчанию эмбеддинги — BAAI/bge-m3.
Требует: собранную SQLite (data/db/business.db).

Использование:
  python scripts/build_rag_index.py
  python scripts/build_rag_index.py --db data/db/business.db --chroma data/chroma
"""
import argparse
import sys
from pathlib import Path

# корень проекта
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка RAG-индексов (DDL + примеры)")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "db" / "business.db", help="Путь к SQLite")
    parser.add_argument("--chroma", type=Path, default=ROOT / "data" / "chroma", help="Папка для Chroma")
    parser.add_argument("--descriptions", type=Path, default=ROOT / "data" / "schema_descriptions.json", help="JSON с описаниями таблиц/колонок")
    parser.add_argument("--examples", type=Path, default=ROOT / "data" / "example_queries.json", help="JSON с примерами запросов")
    parser.add_argument("--no-examples", action="store_true", help="Не индексировать примеры запросов")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Ошибка: база не найдена {args.db}. Сначала выполните: python scripts/build_db.py")
        sys.exit(1)

    desc_path = args.descriptions if args.descriptions.exists() else None
    ex_path = None if args.no_examples else (args.examples if args.examples.exists() else None)

    print("Сборка индексов RAG...")
    result = build_index(
        args.db,
        args.chroma,
        schema_descriptions_path=desc_path,
        example_queries_path=ex_path,
    )
    print(f"  DDL+комментарии: {result['ddl']} чанков")
    print(f"  Примеры запросов: {result['examples']} чанков")
    print(f"Chroma сохранён в {args.chroma}")


if __name__ == "__main__":
    main()
