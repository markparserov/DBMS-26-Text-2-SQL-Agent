"""
Чанки для RAG: DDL+комментарии по таблице, примеры запросов — по одному чанку на пример.
"""
from typing import Any


def build_ddl_chunks(
    ddl_records: list[dict[str, Any]],
    descriptions: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Один чанк = одна таблица: DDL + описание таблицы + описание колонок.
    Возвращает список {"content": str, "metadata": {"table": str, "type": "ddl"}}.
    """
    chunks = []
    for rec in ddl_records:
        table = rec["table"]
        ddl = rec.get("ddl", "")
        columns = rec.get("columns", [])
        desc = descriptions.get(table) or {}
        table_desc = desc.get("description", "") if isinstance(desc, dict) else ""
        col_descs = desc.get("columns", {}) if isinstance(desc, dict) else {}

        parts = [f"## Таблица: {table}"]
        if table_desc:
            parts.append(f"Описание: {table_desc}")
        parts.append("")
        parts.append("```sql")
        parts.append(ddl)
        parts.append("```")
        if columns:
            parts.append("")
            parts.append("Колонки:")
            for c in columns:
                name = c.get("name", "")
                typ = c.get("type", "")
                comment = col_descs.get(name, "") if isinstance(col_descs, dict) else ""
                line = f"  - {name} ({typ})"
                if comment:
                    line += f" — {comment}"
                parts.append(line)

        content = "\n".join(parts)
        chunks.append({
            "content": content,
            "metadata": {"table": table, "type": "ddl"},
        })
    return chunks


def build_example_chunks(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Один чанк = один пример запроса: вопрос + SQL + таблицы/поля.
    Возвращает список {"content": str, "metadata": {"type": "example", "tables": [...]}}.
    """
    chunks = []
    for i, ex in enumerate(examples):
        question = ex.get("question", "")
        sql = ex.get("sql", "")
        tables = ex.get("tables", [])
        columns = ex.get("columns", [])

        parts = ["## Пример запроса"]
        parts.append(f"Вопрос: {question}")
        parts.append("")
        parts.append("```sql")
        parts.append(sql.strip())
        parts.append("```")
        if tables:
            parts.append(f"Таблицы: {', '.join(tables)}")
        if columns:
            parts.append(f"Поля: {', '.join(columns)}")

        content = "\n".join(parts)
        chunks.append({
            "content": content,
            "metadata": {"type": "example", "tables": tables, "index": i},
        })
    return chunks
