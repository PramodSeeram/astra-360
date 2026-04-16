import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from utils.file_helpers import save_upload_file_tmp, remove_tmp_file
from rag.document_processor import process_file
from rag.embeddings import generate_embeddings, generate_single_embedding
from rag.vector_store import insert_documents, search_documents

router = APIRouter(prefix="/rag", tags=["RAG Pipeline"])
logger = logging.getLogger(__name__)

class QueryRequest(BaseModel):
    query: str


def _error_response(message: str, status_code: int):
    return JSONResponse(status_code=status_code, content={"error": message})

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Uploads a document, processes it, creates embeddings, and stores in Vector DB."""
    filename = (file.filename or "").strip()
    normalized_filename = filename.lower()

    if not filename:
        return _error_response("Filename is required.", 400)
    if not normalized_filename.endswith((".pdf", ".csv", ".xls", ".xlsx")):
        return _error_response("Invalid file type. Only PDF, CSV, and Excel allowed.", 400)
        
    file_path = ""
    try:
        file_path = save_upload_file_tmp(file)
        chunks_with_metadata = process_file(file_path, filename)
        logger.info("Chunks created: %s", len(chunks_with_metadata))
        logger.info("Sample chunk preview: %s", chunks_with_metadata[0]["text"][:120].replace("\n", " "))
        
        raw_texts = [chunk["text"] for chunk in chunks_with_metadata]
        vectors = generate_embeddings(raw_texts)
        logger.info("Embedding generation successful: count=%s dimension=%s", len(vectors), len(vectors[0]) if vectors else 0)
        
        insert_documents(chunks_with_metadata, vectors)
        
        return {
            "status": "success", 
            "chunks_processed": len(chunks_with_metadata)
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
    """Embeds user search query and returns top matching document context chunks."""
    try:
        if not payload.query or not payload.query.strip():
            return _error_response("Query must not be empty.", 400)
        query_vector = generate_single_embedding(payload.query)
        results = search_documents(query_vector, top_k=5)
        logger.info("Query results count: %s", len(results))
        
        return {
            "results": results
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
