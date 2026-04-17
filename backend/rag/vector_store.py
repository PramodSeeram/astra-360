import hashlib
import logging
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from typing import List, Dict

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "astra_knowledge_base"
VECTOR_SIZE = 384  # Embedding size for all-MiniLM-L6-v2
logger = logging.getLogger(__name__)

# Initialize the Qdrant Client
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def _generate_stable_point_id(chunk_data: Dict) -> int:
    content = f"{chunk_data['filename']}::{chunk_data['chunk_id']}::{chunk_data['text']}"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _validate_embedding_dimensions(embeddings: List[List[float]]):
    for index, vector in enumerate(embeddings):
        if len(vector) != VECTOR_SIZE:
            raise ValueError(
                f"Invalid embedding dimension at index {index}. Expected {VECTOR_SIZE}, got {len(vector)}."
            )

def init_qdrant_collection():
    """Checks if collection exists, if not, creates it."""
    # Use the newer collections list API
    collections = client.get_collections().collections
    exists = any(col.name == COLLECTION_NAME for col in collections)
    
    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

def insert_documents(chunks_with_metadata: List[Dict], embeddings: List[List[float]]):
    """Stores the text, metadata, and embeddings in Qdrant."""
    init_qdrant_collection()
    _validate_embedding_dimensions(embeddings)
    
    points = []
    for i, (chunk_data, vector) in enumerate(zip(chunks_with_metadata, embeddings)):
        payload = {
            "filename": chunk_data["filename"],
            "chunk_id": chunk_data["chunk_id"],
            "text": chunk_data["text"]
        }
        
        point_id = _generate_stable_point_id(chunk_data)
        
        points.append(
            PointStruct(
                id=point_id, 
                vector=vector, 
                payload=payload
            )
        )
        
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    logger.info("Qdrant upsert successful: collection=%s points=%s", COLLECTION_NAME, len(points))

def search_documents(query_embedding: List[float], top_k: int = 5) -> List[Dict]:
    """Retrieves the most relevant document chunks for a query."""
    init_qdrant_collection()
    if len(query_embedding) != VECTOR_SIZE:
        raise ValueError(
            f"Invalid query embedding dimension. Expected {VECTOR_SIZE}, got {len(query_embedding)}."
        )
    
    # Use query_points instead of the removed search method
    search_result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k
    )
    
    results = []
    # query_points returns a ScoredPoint list in the .points attribute
    for hit in search_result.points:
        results.append({
            "text": hit.payload.get("text"),
            "metadata": {
                "score": hit.score,
                "filename": hit.payload.get("filename"),
                "chunk_id": hit.payload.get("chunk_id")
            }
        })
        
    logger.info("Qdrant search successful: collection=%s results=%s", COLLECTION_NAME, len(results))
    return results
