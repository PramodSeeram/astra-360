import os
import threading
import logging
import httpx
from functools import lru_cache
from typing import Iterable, List

from sentence_transformers import SentenceTransformer

from services.llm_service import LLM_TIMEOUT, get_ollama_headers

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
GPU_EMBED_URL = os.getenv("GPU_EMBED_URL")

_model_lock = threading.Lock()

@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    if GPU_EMBED_URL:
        return None # Using remote
    with _model_lock:
        return SentenceTransformer(EMBEDDING_MODEL_NAME)

def get_embedding_dimension() -> int:
    if GPU_EMBED_URL:
        # Nomic embed text is 768
        return 768
    return int(_get_model().get_sentence_embedding_dimension())

def generate_embeddings(texts: Iterable[str]) -> List[List[float]]:
    clean_texts = [str(text or "").strip() for text in texts if str(text or "").strip()]
    if not clean_texts:
        return []

    if GPU_EMBED_URL:
        try:
            vectors = []
            h = get_ollama_headers()
            remote_model = (os.getenv("EMBEDDING_MODEL") or "nomic-embed-text:latest").strip()
            embed_timeout = max(60.0, float(LLM_TIMEOUT))
            with httpx.Client(timeout=embed_timeout) as client:
                for text in clean_texts:
                    payload = {"model": remote_model, "prompt": text}
                    response = client.post(GPU_EMBED_URL, json=payload, headers=h)
                    response.raise_for_status()
                    # Ollama returns {"embedding": [...]}
                    vectors.append(response.json()["embedding"])
            return vectors
        except Exception as e:
            logger.error(f"Remote embedding failed: {e}. Falling back to local.")
            # If remote fails, fallback to local if possible
            if not _get_model():
                raise # Can't fallback if we didn't load it

    model = _get_model()
    vectors = model.encode(clean_texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]

def generate_single_embedding(text: str) -> List[float]:
    clean_text = str(text or "").strip()
    if not clean_text:
        raise ValueError("Cannot embed empty text.")
    return generate_embeddings([clean_text])[0]

