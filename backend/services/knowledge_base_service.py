import logging
from pathlib import Path
from typing import Dict, List, Optional

from rag.document_processor import chunk_text, parse_document
from rag.embeddings import generate_embeddings, generate_single_embedding
from rag.vector_store import COLLECTION_KNOWLEDGE, search_collection, upsert_knowledge_points

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".csv"}
CATEGORY_HINTS = {
    "scam": ("scam", "fraud", "otp"),
    "insurance": ("insurance", "claim", "policy"),
    "tax": ("tax", "itr", "gst"),
    "finance": ("finance", "investment", "bank", "interest"),
    "cards": ("card", "credit", "swiggy", "cashback", "zomato", "co-brand"),
}


def resolve_knowledge_dir(base_dir: str) -> Path:
    preferred = Path(base_dir) / "qdrant_docs"
    if preferred.exists():
        return preferred

    fallback = Path(base_dir) / "qdrant docs"
    if fallback.exists():
        return fallback

    return preferred


def infer_category(file_name: str) -> str:
    lower_name = file_name.lower()
    if "cards_canonical" in lower_name or lower_name.startswith("cards_"):
        return "cards"
    for category, keywords in CATEGORY_HINTS.items():
        if any(keyword in lower_name for keyword in keywords):
            return category
    return "finance"


def build_chunks_for_file(file_path: Path) -> List[Dict]:
    parsed = parse_document(str(file_path), file_path.name)
    text = (parsed.get("text") or "").strip()
    if not text:
        logger.warning("Skipping %s because no text was extracted", file_path.name)
        return []

    category = infer_category(file_path.name)
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    return [
        {
            "source": file_path.name,
            "category": category,
            "chunk_index": index,
            "text": chunk,
        }
        for index, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def ingest_knowledge_documents(base_dir: str) -> Dict[str, int]:
    docs_dir = resolve_knowledge_dir(base_dir)
    if not docs_dir.exists():
        raise FileNotFoundError(f"Knowledge directory not found: {docs_dir}")

    all_chunks: List[Dict] = []
    processed_files = 0
    skipped_files = 0
    for file_path in sorted(docs_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped_files += 1
            continue
        file_chunks = build_chunks_for_file(file_path)
        if not file_chunks:
            skipped_files += 1
            continue
        processed_files += 1
        all_chunks.extend(file_chunks)

    embeddings = generate_embeddings(chunk["text"] for chunk in all_chunks)
    inserted = upsert_knowledge_points(all_chunks, embeddings, collection_name=COLLECTION_KNOWLEDGE)
    return {
        "processed_files": processed_files,
        "skipped_files": skipped_files,
        "chunks_inserted": inserted,
    }


def upsert_card_knowledge_documents(base_dir: str) -> Dict[str, int]:
    """Idempotently upsert only ``qdrant_docs/cards_canonical.md`` (category ``cards``).

    Safe to call on every boot so card RAG stays aligned with the canonical trio.
    """
    docs_dir = resolve_knowledge_dir(base_dir)
    path = docs_dir / "cards_canonical.md"
    if not path.is_file():
        logger.warning("Card knowledge file missing: %s", path)
        return {"chunks_inserted": 0, "skipped": 1}

    file_chunks = build_chunks_for_file(path)
    if not file_chunks:
        return {"chunks_inserted": 0, "skipped": 1}

    embeddings = generate_embeddings(chunk["text"] for chunk in file_chunks)
    inserted = upsert_knowledge_points(file_chunks, embeddings, collection_name=COLLECTION_KNOWLEDGE)
    logger.info("Card knowledge upserted: %s chunks from cards_canonical.md", inserted)
    return {"chunks_inserted": inserted, "skipped": 0}


MIN_GOOD_SCORE = 0.55
MIN_WEAK_SCORE = 0.35


def retrieve_context(query: str, category: Optional[str], top_k: int = 5) -> Dict:
    """Retrieve KB chunks with diagnostics + a confidence grade.

    The grade lets the answering layer pick one of three strategies:
    ``good`` (ground the LLM answer), ``weak`` (ask a clarifying
    question), or ``none`` (return a safe fallback). Callers should
    never branch on raw string contents.
    """

    query_embedding = generate_single_embedding(query)
    results = search_collection(
        query_embedding=query_embedding,
        top_k=top_k,
        category=category,
        collection_name=COLLECTION_KNOWLEDGE,
    )

    scored = [
        item for item in results
        if item.get("payload") and (item["payload"].get("text") or "").strip()
    ]
    top_score = max((float(item.get("score") or 0.0) for item in scored), default=0.0)
    hit_count = len(scored)

    if hit_count == 0 or top_score < MIN_WEAK_SCORE:
        grade = "none"
    elif top_score < MIN_GOOD_SCORE:
        grade = "weak"
    else:
        grade = "good"

    ordered = sorted(scored, key=lambda item: float(item.get("score") or 0.0), reverse=True)
    chunks = [item["payload"].get("text", "") for item in ordered]
    sources = []
    seen: set[str] = set()
    for item in ordered:
        src = (item.get("payload") or {}).get("source")
        if not src or src in seen:
            continue
        seen.add(src)
        sources.append(src)

    return {
        "results": ordered,
        "context": "\n\n".join(chunk for chunk in chunks if chunk.strip()),
        "top_score": top_score,
        "hit_count": hit_count,
        "grade": grade,
        "category": category,
        "sources": sources,
    }
