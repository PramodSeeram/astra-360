# Astra 360

Astra 360 is an AI-assisted personal finance application: users authenticate with phone OTP, onboard financial context, explore dashboards and insights, and chat with a multi-agent assistant that reasons over transactions, documents, and knowledge retrieved via RAG (vector search).

The repository is split into a **FastAPI** backend (`backend/`) and a **Vite + React** web UI (`MainUI/`).

## What’s in the box

- **Authentication and user profile** — OTP-based sign-in (Twilio optional for real SMS; otherwise OTP is logged for development).
- **Onboarding and data** — Upload and activation flows for financial data tied to the user.
- **Dashboard and insights** — Aggregated views and generated insights stored and surfaced through the API.
- **Chat** — Conversational assistant with routing to specialized agents (spending, credit, cards, fraud, and more) backed by LangGraph.
- **RAG** — Embeddings (sentence-transformers) and Qdrant for knowledge and document retrieval.
- **LLM** — HTTP API compatible with Ollama’s `/api/generate` by default (`LLM_URL` / `LLM_MODEL`).

## Repository layout

| Path | Role |
|------|------|
| `backend/` | FastAPI app, SQLAlchemy models, agents, RAG, routes |
| `MainUI/` | React SPA (Vite, TypeScript, Tailwind, shadcn-style UI) |
| `docker/` | Optional Dockerfiles and `docker-compose` for containerized runs |

## Prerequisites

- **Python** 3.10+ (matches `docker/backend.Dockerfile`)
- **Node.js** 18+ (for the UI; use a current LTS if unsure)
- **MySQL** — a reachable database; connection string via `DATABASE_URL` in `backend/.env`
- **Qdrant** — vector DB on `localhost:6333` by default (or set `QDRANT_HOST` / `QDRANT_PORT`)
- **LLM** — an Ollama-compatible server reachable at `LLM_URL` (default `http://localhost:11434/api/generate`) with the model named in `LLM_MODEL`

## Run locally (recommended)

Run the **backend first**, then the **UI**. The dev server proxies API calls to the backend so the browser stays same-origin in development.

1. **Backend** — See [backend/README.md](backend/README.md) for creating a virtual environment, installing dependencies, configuring `.env`, and starting Uvicorn.

2. **Frontend** — See [MainUI/README.md](MainUI/README.md) for `npm install`, `npm run dev`, ports, and production build notes.

Default ports used in config: backend **8000**, UI dev server **8080** (see each README).

## Optional: Docker

`docker/docker-compose.yml` defines MySQL, backend, and UI services. The backend expects `DATABASE_URL` in its environment (see [backend/README.md](backend/README.md)); adjust compose or env files before relying on it in production.

## Documentation

- [MainUI/README.md](MainUI/README.md) — install, dev server, build, proxy and `VITE_API_BASE`
- [backend/README.md](backend/README.md) — Python env, `.env` variables, migrations, running the API
