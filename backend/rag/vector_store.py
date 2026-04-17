import hashlib
import logging
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, Range
from typing import List, Dict, Optional, Any

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

# Multi-collection design
COLLECTION_DOCUMENTS = "astra_documents_v2"
COLLECTION_TRANSACTIONS = "astra_transactions_v2"
COLLECTION_INSIGHTS = "astra_insights_v2"
VECTOR_SIZE = 768  # Embedding size for nomic-embed-text

logger = logging.getLogger(__name__)

# Initialize the Qdrant Client
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def _generate_stable_point_id(content: str) -> int:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)

def _validate_embedding_dimensions(embeddings: List[List[float]]):
    for index, vector in enumerate(embeddings):
        if not vector:
            raise ValueError(f"Invalid embedding at index {index}: empty vector.")
        if len(vector) != VECTOR_SIZE:
            raise ValueError(
                f"Invalid embedding dimension. Expected {VECTOR_SIZE}, got {len(vector)}."
            )

def init_qdrant_collections():
    """Checks if collections exist, if not, creates them."""
    collections = [c.name for c in client.get_collections().collections]
    
    for coll_name in [COLLECTION_DOCUMENTS, COLLECTION_TRANSACTIONS, COLLECTION_INSIGHTS]:
        if coll_name not in collections:
            client.create_collection(
                collection_name=coll_name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {coll_name}")

def insert_documents(chunks_with_metadata: List[Dict], embeddings: List[List[float]]):
    """Stores the text, metadata, and embeddings for documents in astra_documents."""
    init_qdrant_collections()
    _validate_embedding_dimensions(embeddings)
    
    points = []
    for chunk_data, vector in zip(chunks_with_metadata, embeddings):
        payload = {
            "type": "document_chunk",
            "filename": chunk_data.get("filename"),
            "chunk_id": chunk_data.get("chunk_id"),
            "text": chunk_data.get("text")
        }
        
        content = f"{chunk_data.get('filename')}::{chunk_data.get('chunk_id')}::{chunk_data.get('text')}"
        point_id = _generate_stable_point_id(content)
        
        points.append(
            PointStruct(
                id=point_id, 
                vector=vector, 
                payload=payload
            )
        )
        
    if points:
        client.upsert(
            collection_name=COLLECTION_DOCUMENTS,
            points=points
        )
        logger.info(f"Qdrant upsert successful: collection={COLLECTION_DOCUMENTS} points={len(points)}")

def insert_transactions(transactions: List[Dict], embeddings: List[List[float]]):
    """Stores the structured payload and semantic text for transactions in astra_transactions."""
    if len(transactions) != len(embeddings):
        raise ValueError(
            f"Transaction/vector count mismatch: {len(transactions)} transactions, {len(embeddings)} embeddings."
        )
    init_qdrant_collections()
    _validate_embedding_dimensions(embeddings)
    
    points = []
    for tx, vector in zip(transactions, embeddings):
        if not tx.get("text"):
            raise ValueError("Transaction payload must include semantic text.")
        # The payload includes all structured metadata required for filtering
        point_id = _generate_stable_point_id(tx.get('tx_hash', str(tx)))
        points.append(
            PointStruct(
                id=point_id, 
                vector=vector, 
                payload=tx
            )
        )
        
    if points:
        client.upsert(
            collection_name=COLLECTION_TRANSACTIONS,
            points=points
        )
        logger.info(f"Qdrant upsert successful: collection={COLLECTION_TRANSACTIONS} points={len(points)}")

def insert_insight(insight_text: str, metadata: Dict[str, Any], embedding: List[float]):
    """Stores derived insights in astra_insights."""
    if not insight_text or not insight_text.strip():
        raise ValueError("Insight text must not be empty.")
    init_qdrant_collections()
    _validate_embedding_dimensions([embedding])
    
    payload = {"text": insight_text, "type": "insight"}
    payload.update(metadata)
    
    point_id = _generate_stable_point_id(insight_text)
    
    client.upsert(
        collection_name=COLLECTION_INSIGHTS,
        points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
    )

def search_knowledge(
    collection_name: str,
    query_embedding: List[float], 
    top_k: int = 5,
    filter_conditions: Optional[Filter] = None
) -> List[Dict]:
    """Retrieves relevant chunks/transactions directly from Qdrant."""
    init_qdrant_collections()
    _validate_embedding_dimensions([query_embedding])
    
    search_result = client.query_points(
        collection_name=collection_name,
        query=query_embedding,
        query_filter=filter_conditions,
        limit=top_k
    )
    
    results = []
    for hit in search_result.points:
        results.append({
            "payload": hit.payload,
            "score": hit.score
        })
        
    logger.info(f"Qdrant search: collection={collection_name} results={len(results)}")
    return results

# Helper for filter generation
def create_category_filter(category: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="category", match=MatchValue(value=category))
        ]
    )

def create_date_range_filter(start_date: str, end_date: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="date", range=Range(gte=start_date, lte=end_date))
        ]
    )
