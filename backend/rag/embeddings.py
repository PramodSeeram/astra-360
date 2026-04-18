import threading
from functools import lru_cache
from typing import Iterable, List

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model_lock = threading.Lock()


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    with _model_lock:
        return SentenceTransformer(EMBEDDING_MODEL_NAME)


def get_embedding_dimension() -> int:
    return int(_get_model().get_sentence_embedding_dimension())


def generate_embeddings(texts: Iterable[str]) -> List[List[float]]:
    clean_texts = [str(text or "").strip() for text in texts if str(text or "").strip()]
    if not clean_texts:
        return []
    vectors = _get_model().encode(clean_texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def generate_single_embedding(text: str) -> List[float]:
    clean_text = str(text or "").strip()
    if not clean_text:
        raise ValueError("Cannot embed empty text.")
    return generate_embeddings([clean_text])[0]
