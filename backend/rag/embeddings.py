from sentence_transformers import SentenceTransformer
from typing import List

MODEL_NAME = "all-MiniLM-L6-v2"

# Load the model globally so it isn't repeatedly initialized
model = SentenceTransformer(MODEL_NAME)

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Converts a list of text chunks into embedding vectors."""
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()

def generate_single_embedding(text: str) -> List[float]:
    """Converts a single query string into an embedding vector."""
    embedding = model.encode([text], convert_to_numpy=True)
    return embedding[0].tolist()
