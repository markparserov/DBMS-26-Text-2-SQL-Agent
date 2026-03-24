"""
Эмбеддинги через BAAI/bge-m3 (локально, sentence-transformers).
"""
import os
from typing import List

# Убираем предупреждение HF Hub и лишний вывод при загрузке (до любого импорта HF)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


def get_embeddings(texts: List[str], model: str = DEFAULT_EMBEDDING_MODEL) -> List[List[float]]:
    """Возвращает список векторов для списка текстов (BGE-M3)."""
    return _get_embeddings_bge_m3(texts, model)


def _get_embeddings_bge_m3(texts: List[str], model: str = "BAAI/bge-m3") -> List[List[float]]:
    """Локальные эмбеддинги через sentence-transformers (BGE-M3)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError("Установите sentence-transformers для BGE-M3: pip install sentence-transformers")

    if not hasattr(_get_embeddings_bge_m3, "_model"):
        _tqdm = os.environ.get("TQDM_DISABLE")
        os.environ["TQDM_DISABLE"] = "1"
        try:
            _get_embeddings_bge_m3._model = SentenceTransformer(model)
        finally:
            if _tqdm is None:
                os.environ.pop("TQDM_DISABLE", None)
            else:
                os.environ["TQDM_DISABLE"] = _tqdm

    m = _get_embeddings_bge_m3._model
    try:
        embeddings = m.encode(texts, batch_size=32, show_progress_bar=False)
    except TypeError:
        embeddings = m.encode(texts, batch_size=32)
    return embeddings.tolist()
