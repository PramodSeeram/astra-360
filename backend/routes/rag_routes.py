import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from utils.file_helpers import save_upload_file_tmp, remove_tmp_file
from rag.embeddings import generate_single_embedding
from rag.vector_store import (
    search_knowledge,
    COLLECTION_DOCUMENTS,
    COLLECTION_INSIGHTS,
    COLLECTION_TRANSACTIONS,
)
from services.data_activation_service import extract_bank_transactions_async, vectorize_financial_rag_async

router = APIRouter(prefix="/rag", tags=["RAG Pipeline"])
logger = logging.getLogger(__name__)

class QueryRequest(BaseModel):
    query: str


def _error_response(message: str, status_code: int):
    return JSONResponse(status_code=status_code, content={"error": message})

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Uploads a bank statement and stores structured financial RAG data in Qdrant."""
    filename = (file.filename or "").strip()
    normalized_filename = filename.lower()

    if not filename:
        return _error_response("Filename is required.", 400)
    if not normalized_filename.endswith((".pdf", ".csv", ".xls", ".xlsx")):
        return _error_response("Invalid file type. Only PDF, CSV, and Excel allowed.", 400)
        
    file_path = ""
    try:
        file_path = save_upload_file_tmp(file)
        transactions, extraction_meta = await extract_bank_transactions_async(file_path, filename)
        logger.info(
            "Financial extraction complete: method=%s raw=%s valid=%s",
            extraction_meta["method"],
            extraction_meta["raw_count"],
            extraction_meta["valid_count"],
        )

        if not transactions:
            return _error_response("No financial transactions could be extracted from this statement.", 400)

        vector_counts = await vectorize_financial_rag_async(transactions, filename)
        
        return {
            "status": "success", 
            "transactions_processed": len(transactions),
            "transactions_vectorized": vector_counts["transactions"],
            "insights_vectorized": vector_counts["insights"],
            "extraction_method": extraction_meta["method"],
        }
    except ValueError as exc:
        logger.error("RAG upload validation failed: %s", exc)
        return _error_response(str(exc), 400)
    except HTTPException as exc:
        logger.error("RAG upload HTTP error: %s", exc.detail)
        return _error_response(str(exc.detail), exc.status_code)
    except Exception:
        logger.exception("RAG upload failed")
        return _error_response("Failed to process upload.", 500)
    finally:
        if file_path:
            remove_tmp_file(file_path)

@router.post("/query")
async def query_knowledge_base(payload: QueryRequest):
    """Embeds a query and returns grounded financial RAG context."""
    try:
        if not payload.query or not payload.query.strip():
            return _error_response("Query must not be empty.", 400)
        query_vector = generate_single_embedding(payload.query)
        transactions = search_knowledge(COLLECTION_TRANSACTIONS, query_vector, top_k=5)
        insights = search_knowledge(COLLECTION_INSIGHTS, query_vector, top_k=3)
        documents = search_knowledge(COLLECTION_DOCUMENTS, query_vector, top_k=2)
        logger.info(
            "RAG query results: transactions=%s insights=%s documents=%s",
            len(transactions),
            len(insights),
            len(documents),
        )
        
        return {
            "transactions": transactions,
            "insights": insights,
            "documents": documents,
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
