import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from rag.embeddings import get_embedding_dimension

logger = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

COLLECTION_KNOWLEDGE = "astra_knowledge"
COLLECTION_TRANSACTIONS = "astra_transactions"
COLLECTION_INSIGHTS = "astra_insights"
COLLECTION_DOCUMENTS = "astra_documents"

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)


def _point_id(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def create_category_filter(category: str) -> Filter:
    return Filter(
        must=[FieldCondition(key="category", match=MatchValue(value=category))]
    )


def ensure_collection(collection_name: str = COLLECTION_KNOWLEDGE) -> None:
    dimension = get_embedding_dimension()
    try:
        collections = {item.name for item in client.get_collections().collections}
        if collection_name in collections:
            return

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s' with dimension=%s", collection_name, dimension)
    except Exception as e:
        logger.error(f"Error ensuring collection {collection_name}: {e}")


def upsert_knowledge_points(
    chunks_with_metadata: List[Dict[str, Any]],
    embeddings: List[List[float]],
    collection_name: str = COLLECTION_KNOWLEDGE,
) -> int:
    if len(chunks_with_metadata) != len(embeddings):
        raise ValueError("Chunk and embedding count mismatch.")

    ensure_collection(collection_name)

    points: List[PointStruct] = []
    for chunk, vector in zip(chunks_with_metadata, embeddings):
        point_seed = f"{chunk['source']}::{chunk['chunk_index']}::{chunk['text']}"
        payload = {
            "source": chunk["source"],
            "category": chunk["category"],
            "chunk_index": chunk["chunk_index"],
            "text": chunk["text"],
        }
        points.append(PointStruct(id=_point_id(point_seed), vector=vector, payload=payload))

    if not points:
        return 0

    client.upsert(collection_name=collection_name, points=points)
    logger.info("Upserted %s knowledge chunks into '%s'", len(points), collection_name)
    return len(points)


def category_filter(category: Optional[str]) -> Optional[Filter]:
    if not category:
        return None
    return create_category_filter(category)


def search_collection(
    query_embedding: List[float],
    top_k: int = 5,
    category: Optional[str] = None,
    collection_name: str = COLLECTION_KNOWLEDGE,
) -> List[Dict[str, Any]]:
    ensure_collection(collection_name)
    results = client.query_points(
        collection_name=collection_name,
        query=query_embedding,
        query_filter=category_filter(category),
        limit=top_k,
    )
    return [
        {
            "score": point.score,
            "payload": dict(point.payload or {}),
        }
        for point in results.points
    ]


def search_knowledge(
    collection_name: str,
    query_embedding: List[float],
    top_k: int = 5,
    filter_conditions: Optional[Filter] = None,
) -> List[Dict[str, Any]]:
    """Generic search function expected by wealth_agent.py"""
    ensure_collection(collection_name)
    try:
        results = client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            query_filter=filter_conditions,
            limit=top_k,
        )
        return [
            {
                "score": point.score,
                "payload": dict(point.payload or {}),
            }
            for point in results.points
        ]
    except Exception as e:
        logger.error(f"Search error in {collection_name}: {e}")
        return []
