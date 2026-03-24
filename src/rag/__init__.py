"""
RAG по схеме БД и примерам запросов.
- Индекс 1: DDL + комментарии к таблицам/колонкам (чанк на таблицу).
- Индекс 2 (опционально): примеры запросов (вопрос + SQL + сущности).
"""
from .schema import get_ddl_from_sqlite, load_schema_descriptions, load_example_queries
from .index import RAGIndex, build_index, search

__all__ = [
    "get_ddl_from_sqlite",
    "load_schema_descriptions",
    "load_example_queries",
    "RAGIndex",
    "build_index",
    "search",
]
