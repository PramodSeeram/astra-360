import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.agent_router import route_query
from services.knowledge_base_service import ingest_knowledge_documents, retrieve_context

router = APIRouter(prefix="/rag", tags=["RAG Pipeline"])
logger = logging.getLogger(__name__)

class QueryRequest(BaseModel):
    query: str


def _error_response(message: str, status_code: int):
    return JSONResponse(status_code=status_code, content={"error": message})

@router.post("/ingest")
async def ingest_knowledge():
    try:
        project_root = Path(__file__).resolve().parents[2]
        return ingest_knowledge_documents(str(project_root))
    except Exception as exc:
        logger.exception("Knowledge ingestion failed")
        return _error_response(str(exc), 500)

@router.post("/query")
async def query_knowledge_base(payload: QueryRequest):
    """Embeds a query and returns grounded knowledge context."""
    try:
        if not payload.query or not payload.query.strip():
            return _error_response("Query must not be empty.", 400)
        route = route_query(payload.query)
        if route.agent == "finance_agent":
            return {
                "agent": route.agent,
                "category": route.category,
                "results": [],
                "context": "",
            }
        retrieval = retrieve_context(payload.query, category=route.category, top_k=5)
        return {
            "agent": route.agent,
            "category": route.category,
            "results": retrieval.get("results", []),
            "context": retrieval.get("context", ""),
            "top_score": retrieval.get("top_score", 0.0),
            "hit_count": retrieval.get("hit_count", 0),
            "grade": retrieval.get("grade", "none"),
            "sources": retrieval.get("sources", []),
        }
    except ValueError as exc:
        logger.error("RAG query validation failed: %s", exc)
        return _error_response(str(exc), 400)
    except HTTPException as exc:
        logger.error("RAG query HTTP error: %s", exc.detail)
        return _error_response(str(exc.detail), exc.status_code)
    except Exception:
        logger.exception("RAG query failed")
        return _error_response("Failed to process query.", 500)
