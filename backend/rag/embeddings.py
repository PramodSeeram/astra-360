import os
import httpx
import logging
import asyncio
from typing import List, Dict

logger = logging.getLogger(__name__)

# GPU Server API Endpoint
GPU_EMBED_URL = os.getenv("GPU_EMBED_URL", "https://0ruool8gerdycr-11434.proxy.runpod.net/api/embeddings")
OLLAMA_ROOT_URL = GPU_EMBED_URL.replace("/api/embeddings", "")

MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
CONCURRENCY_LIMIT = 5
TIMEOUT = 60.0

_embedding_cache: Dict[str, List[float]] = {}
_sem = None

async def _health_check(client: httpx.AsyncClient):
    try:
        r = await client.get(OLLAMA_ROOT_URL, timeout=10.0, headers={"Authorization": "Bearer runpod"})
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"Ollama Health Check failed: {e}")

async def _fetch_single_embedding(client: httpx.AsyncClient, text: str) -> List[float]:
    """Fetches a single embedding."""
    if not text.strip():
        raise ValueError("Cannot embed empty text.")
        
    if text in _embedding_cache:
        return _embedding_cache[text]

    payload = {
        "model": "nomic-embed-text",
        "prompt": text,
        "stream": False
    }
    
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
        
    async with _sem:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.post(
                    GPU_EMBED_URL, 
                    json=payload, 
                    timeout=TIMEOUT,
                    headers={"Authorization": "Bearer runpod"}
                )
                response.raise_for_status()
                data = response.json()
                if "embedding" not in data:
                    raise ValueError(f"Invalid response format: {data}")
                
                emb = data["embedding"]
                if not isinstance(emb, list) or not emb:
                    raise ValueError("Embedding response contained an empty vector.")
                _embedding_cache[text] = emb
                return emb
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"GPU API HTTP Error {e.response.status_code} on attempt {attempt}: {e.response.text}")
                if attempt == MAX_RETRIES:
                    raise
            except (httpx.RequestError, ValueError) as e:
                logger.warning(f"GPU API Request Error on attempt {attempt}: {e}")
                if attempt == MAX_RETRIES:
                    raise
                    
            await asyncio.sleep(INITIAL_BACKOFF * (2 ** (attempt - 1)))
            
    return []

async def generate_embeddings_async(texts: List[str]) -> List[List[float]]:
    """Converts texts into embedding vectors one-by-one through Ollama."""
    if not texts:
        return []
        
    async with httpx.AsyncClient() as client:
        await _health_check(client)
        results = []
        for text in texts:
            results.append(await _fetch_single_embedding(client, text))
            
    return results

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Synchronous wrapper for generate_embeddings_async. Blocks until completion."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Fallback if already running
        import threading
        result = []
        def run_in_thread():
            result.append(asyncio.run(generate_embeddings_async(texts)))
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return result[0]
    else:
        return asyncio.run(generate_embeddings_async(texts))

def generate_single_embedding(text: str) -> List[float]:
    """Converts a single query string into an embedding vector."""
    embeddings = generate_embeddings([text])
    if not embeddings:
        raise RuntimeError("Failed to retrieve embedding for the query.")
    return embeddings[0]
