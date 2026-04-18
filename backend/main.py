import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
from database import engine, Base
import models # Ensure models are loaded for metadata
from sqlalchemy import inspect, text

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)
logger = logging.getLogger(__name__)


# Idempotent column bootstrap for demo-friendly upgrades.
# create_all does not add columns to existing tables, so we patch missing ones
# that later code relies on (statement balance, card linkage, KYC flags).
def _ensure_columns() -> None:
    inspector = inspect(engine)

    def cols(table: str) -> set[str]:
        try:
            return {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return set()

    additions = [
        ("transactions", "statement_balance", "FLOAT"),
        ("transactions", "card_id", "INTEGER"),
        ("users", "pan", "VARCHAR(20)"),
        ("users", "kyc_completed", "INTEGER DEFAULT 0"),
    ]
    with engine.begin() as conn:
        for table, column, sql_type in additions:
            if column in cols(table):
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
            except Exception:
                pass


_ensure_columns()


def _ensure_knowledge_base() -> None:
    """Best-effort one-time ingest so demo RAG has data on first boot."""
    try:
        from rag.vector_store import COLLECTION_KNOWLEDGE, client as qdrant_client

        info = qdrant_client.get_collection(COLLECTION_KNOWLEDGE)
        points = int(getattr(info, "points_count", 0) or 0)
        if points > 0:
            logger.info("Knowledge collection already populated (%s points).", points)
            return
    except Exception:
        # Missing collection or qdrant startup race — try ingest below.
        pass

    try:
        from services.knowledge_base_service import ingest_knowledge_documents

        project_root = str(Path(__file__).resolve().parent.parent)
        stats = ingest_knowledge_documents(project_root)
        logger.info("Knowledge ingest completed: %s", stats)
    except Exception as exc:
        logger.warning("Knowledge ingest skipped: %s", exc)

    try:
        from services.knowledge_base_service import upsert_card_knowledge_documents

        project_root = str(Path(__file__).resolve().parent.parent)
        card_stats = upsert_card_knowledge_documents(project_root)
        logger.info("Card knowledge upsert: %s", card_stats)
    except Exception as exc:
        logger.warning("Card knowledge upsert skipped: %s", exc)


_ensure_knowledge_base()

from routes.auth import router as auth_router
from routes.user import router as user_router
from routes.onboarding import router as onboarding_router
from routes.dashboard import router as dashboard_router
from routes.rag_routes import router as rag_router
from routes.chat_routes import router as chat_router
from routes.insurance_routes import router as insurance_router
from routes.data import router as data_router
from routes.dev import router as dev_router
from routes.insights import router as insights_router


app = FastAPI(title="Astra 360 Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(onboarding_router)
app.include_router(dashboard_router)
app.include_router(rag_router)
app.include_router(chat_router)
app.include_router(insurance_router)
app.include_router(data_router)
app.include_router(dev_router)
app.include_router(insights_router)


@app.get("/")
def root():
    return {"status": "Astra 360 Backend Running"}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on {host}:{port} loaded from .env...")
    uvicorn.run("main:app", host=host, port=port, reload=True)
