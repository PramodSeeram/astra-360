# Astra 360 — Backend

FastAPI service for authentication, user and financial data, dashboards, RAG, insurance-related routes, chat with a LangGraph multi-agent pipeline, and dev utilities.

## Requirements

- Python **3.10+**
- **MySQL** (via PyMySQL; URL in `DATABASE_URL`)
- **Qdrant** for vector storage (default `localhost:6333`)
- An **LLM** endpoint compatible with Ollama’s `POST /api/generate` (see `services/llm_service.py`)

## Setup

### 1. Virtual environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

Copy the example file and edit values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | **Yes** | SQLAlchemy URL, e.g. `mysql+pymysql://user:password@127.0.0.1:3306/astra` |
| `HOST` | No | Bind address (default `0.0.0.0`) |
| `PORT` | No | Port (default `8000`) |
| `QDRANT_HOST` | No | Qdrant host (default `localhost`) |
| `QDRANT_PORT` | No | Qdrant port (default `6333`) |
| `QDRANT_API_KEY` | No | If your Qdrant instance uses API key auth |
| `LLM_URL` | No | Default `http://localhost:11434/api/generate` |
| `LLM_MODEL` | No | Default `astra-llm:latest` (see also `OLLAMA_MODEL`) |
| `MY_REAL_PHONE` | No | 10-digit Indian number without country code; only this number gets real Twilio SMS if Twilio is configured |
| `TWILIO_*` | No | Optional; for real OTP SMS (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`) |
| `USE_MULTI_AGENT` | No | Chat multi-agent graph (default on) |
| `USE_AGENTIC_CHAT` | No | Agentic chat loop (default on) |
| `AGENTIC_DEBUG` | No | Verbose agent logging |
| `CATEGORY_TIMEOUT_SECONDS` / `CATEGORY_CONCURRENCY` | No | Data activation tuning |

On startup the app creates tables (and patches some columns), may ingest knowledge into Qdrant if collections are empty, and exposes OpenAPI at `/docs`.

### 3. Run the server

From the `backend` directory with the virtual environment active:

```bash
python main.py
```

This starts Uvicorn with reload using `HOST` and `PORT` from `.env`.

Alternatively:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check: open `http://127.0.0.1:8000/` — you should see a JSON status payload.

### 4. Database migrations (optional)

Alembic is configured under `alembic/`. Ensure `DATABASE_URL` is set, then from `backend/`:

```bash
alembic upgrade head
```

## Supporting services

- **Qdrant** — Run locally, for example: `docker run -p 6333:6333 qdrant/qdrant` (see [Qdrant docs](https://qdrant.tech/documentation/guides/installation/)).
- **Ollama** (or any compatible server) — Serve the model referenced by `LLM_MODEL` at `LLM_URL`.

Embeddings use `sentence-transformers` (`all-MiniLM-L6-v2`); the first run downloads the model.

## Project notes

- API title: `Astra 360 Backend` (see `main.py`).
- CORS is permissive (`allow_origins=["*"]`) for local development; tighten for production.
