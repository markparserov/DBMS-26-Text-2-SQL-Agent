"""
Построение и поиск по индексам RAG (Chroma + эмбеддинги BGE-M3).
Индекс 1: DDL + комментарии. Индекс 2 (опционально): примеры запросов.
"""
from pathlib import Path
from typing import Any

from .chunks import build_ddl_chunks, build_example_chunks
from .embeddings import get_embeddings
from .schema import (
    get_ddl_from_sqlite,
    load_example_queries,
    load_schema_descriptions,
)


def _get_chroma():
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        raise ImportError("Установите chromadb: pip install chromadb")
    return chromadb, Settings


class RAGIndex:
    """
    Два коллекции Chroma: ddl (схема+комментарии) и examples (примеры запросов).
    """

    def __init__(self, persist_directory: str | Path) -> None:
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        chromadb, Settings = _get_chroma()
        self._client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False),
        )
        self._ddl_collection = self._client.get_or_create_collection(
            "ddl",
            metadata={"description": "DDL + комментарии по таблицам"},
        )
        self._examples_collection = self._client.get_or_create_collection(
            "examples",
            metadata={"description": "Примеры запросов"},
        )

    def build_ddl_index(
        self,
        db_path: str | Path,
        descriptions_path: str | Path | None = None,
        embedding_model: str = "BAAI/bge-m3",
    ) -> int:
        """Индексирует DDL + комментарии. Возвращает число чанков."""
        ddl_records = get_ddl_from_sqlite(db_path)
        descriptions = load_schema_descriptions(descriptions_path)
        chunks = build_ddl_chunks(ddl_records, descriptions)
        if not chunks:
            return 0
        texts = [c["content"] for c in chunks]
        ids = [f"ddl_{c['metadata']['table']}" for c in chunks]
        embeddings = get_embeddings(texts, model=embedding_model)
        meta = [c["metadata"] for c in chunks]
        existing = self._ddl_collection.get()
        if existing["ids"]:
            self._ddl_collection.delete(ids=existing["ids"])
        self._ddl_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=meta,
        )
        return len(chunks)

    def build_examples_index(
        self,
        examples_path: str | Path,
        embedding_model: str = "BAAI/bge-m3",
    ) -> int:
        """Индексирует примеры запросов. Возвращает число чанков."""
        examples = load_example_queries(examples_path)
        if not examples:
            return 0
        chunks = build_example_chunks(examples)
        texts = [c["content"] for c in chunks]
        ids = [f"ex_{c['metadata']['index']}" for c in chunks]
        embeddings = get_embeddings(texts, model=embedding_model)
        # Chroma принимает только str/int/float в metadata
        meta = []
        for c in chunks:
            m = {"type": "example", "index": c["metadata"]["index"]}
            if c["metadata"].get("tables"):
                m["tables"] = ",".join(c["metadata"]["tables"])
            meta.append(m)
        existing = self._examples_collection.get()
        if existing["ids"]:
            self._examples_collection.delete(ids=existing["ids"])
        self._examples_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=meta,
        )
        return len(chunks)

    def search(
        self,
        question: str,
        k_ddl: int = 5,
        k_examples: int = 2,
        embedding_model: str = "BAAI/bge-m3",
    ) -> dict[str, Any]:
        """
        Поиск по вопросу. Возвращает:
        {
          "ddl_chunks": [{"content": ..., "metadata": ...}, ...],
          "example_chunks": [...],
          "context_for_prompt": str  # готовый блок для промпта
        }
        """
        [q_emb] = get_embeddings([question], model=embedding_model)

        ddl_chunks = []
        n_ddl = self._ddl_collection.count()
        if n_ddl > 0:
            ddl_results = self._ddl_collection.query(
                query_embeddings=[q_emb],
                n_results=min(k_ddl, n_ddl),
                include=["documents", "metadatas"],
            )
            if ddl_results["documents"] and ddl_results["documents"][0]:
                for doc, meta in zip(ddl_results["documents"][0], ddl_results["metadatas"][0] or []):
                    ddl_chunks.append({"content": doc, "metadata": meta or {}})

        example_chunks = []
        n_ex = self._examples_collection.count()
        if n_ex > 0 and k_examples > 0:
            ex_results = self._examples_collection.query(
                query_embeddings=[q_emb],
                n_results=min(k_examples, n_ex),
                include=["documents", "metadatas"],
            )
            if ex_results["documents"] and ex_results["documents"][0]:
                for doc, meta in zip(ex_results["documents"][0], ex_results["metadatas"][0] or []):
                    example_chunks.append({"content": doc, "metadata": meta or {}})

        context_for_prompt = _format_context_for_prompt(ddl_chunks, example_chunks)
        return {
            "ddl_chunks": ddl_chunks,
            "example_chunks": example_chunks,
            "context_for_prompt": context_for_prompt,
        }


def _format_context_for_prompt(
    ddl_chunks: list[dict],
    example_chunks: list[dict],
) -> str:
    """Собирает блок контекста для промпта: DDL + комментарии + 1–2 примера; явно перечисляет таблицы и поля."""
    sections = []
    tables_mentioned = set()

    if ddl_chunks:
        sections.append("### Схема БД (таблицы и поля, на которые можно ссылаться)\n")
        for c in ddl_chunks:
            sections.append(c["content"])
            sections.append("")
            meta = c.get("metadata") or {}
            if meta.get("table"):
                tables_mentioned.add(meta["table"])

    if example_chunks:
        sections.append("### Релевантные примеры запросов\n")
        for c in example_chunks:
            sections.append(c["content"])
            sections.append("")
            meta = c.get("metadata") or {}
            if meta.get("tables"):
                for t in str(meta["tables"]).split(","):
                    tables_mentioned.add(t.strip())

    if tables_mentioned:
        sections.append("---")
        sections.append("**Используемые сущности:** таблицы: " + ", ".join(sorted(tables_mentioned)))

    return "\n".join(sections).strip()


def build_index(
    db_path: str | Path,
    persist_directory: str | Path,
    *,
    schema_descriptions_path: str | Path | None = None,
    example_queries_path: str | Path | None = None,
    embedding_model: str = "BAAI/bge-m3",
) -> dict[str, int]:
    """
    Собирает оба индекса. Возвращает {"ddl": N, "examples": M}.
    """
    index = RAGIndex(persist_directory)
    n_ddl = index.build_ddl_index(db_path, schema_descriptions_path, embedding_model)
    n_ex = 0
    if example_queries_path and Path(example_queries_path).exists():
        n_ex = index.build_examples_index(example_queries_path, embedding_model)
    return {"ddl": n_ddl, "examples": n_ex}


def search(
    question: str,
    persist_directory: str | Path,
    *,
    k_ddl: int = 5,
    k_examples: int = 2,
    embedding_model: str = "BAAI/bge-m3",
) -> dict[str, Any]:
    """Один общий запрос к RAG перед генерацией SQL."""
    index = RAGIndex(persist_directory)
    return index.search(question, k_ddl=k_ddl, k_examples=k_examples, embedding_model=embedding_model)
