"""
Извлечение DDL из SQLite и загрузка описаний/примеров запросов.
SQLite не хранит COMMENT ON — комментарии берём из отдельного файла.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any


def get_ddl_from_sqlite(db_path: str | Path) -> list[dict[str, Any]]:
    """
    Читает из SQLite DDL всех таблиц (CREATE TABLE) и информацию о колонках.
    Возвращает список: [ {"table": "t1", "ddl": "CREATE TABLE ...", "columns": [{"name": "a", "type": "INTEGER"}, ...]}, ... ]
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"База не найдена: {db_path}")

    result = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        for row in cur:
            name = row["name"]
            sql = row["sql"] or ""
            # PRAGMA table_info не поддерживает плейсхолдер ?; имя таблицы из sqlite_master — экранируем кавычки
            safe_name = name.replace('"', '""')
            cur2 = conn.execute(f'PRAGMA table_info("{safe_name}")')
            columns = [{"name": r[1], "type": r[2] or ""} for r in cur2]
            result.append({"table": name, "ddl": sql, "columns": columns})
    return result


def load_schema_descriptions(path: str | Path | None) -> dict[str, Any]:
    """
    Загружает описания таблиц и колонок из JSON.
    Формат:
    {
      "tables": {
        "table_name": {
          "description": "Описание таблицы",
          "columns": {
            "col_name": "Описание колонки"
          }
        }
      }
    }
    Если файла нет — возвращается пустой dict.
    """
    if path is None:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("tables", raw) if isinstance(raw, dict) else {}


def load_example_queries(path: str | Path | None) -> list[dict[str, Any]]:
    """
    Загружает каталог примеров запросов из JSON.
    Формат — массив:
    [
      {
        "question": "Вопрос на естественном языке",
        "sql": "SELECT ...",
        "tables": ["table1", "table2"],
        "columns": ["table1.col1", "table2.col2"]
      }
    ]
    Поля tables/columns опциональны.
    Если файла нет — пустой list.
    """
    if path is None:
        return []
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "examples" in raw:
        return raw["examples"]
    return []
