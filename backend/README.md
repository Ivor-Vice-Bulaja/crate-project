# backend/

The Python backend for Crate. Built with FastAPI and served via uvicorn.

## What belongs here

- `main.py` — FastAPI app entry point. Creates the app instance, registers routers, starts the server.
- `config.py` — Centralised settings loaded from `.env`. Every module that needs config imports from here.
- `database.py` — SQLite connection, schema creation, and migrations.
- `api/` — HTTP route handlers. One file per resource group (tracks, crates, search).
- `importer/` — The import pipeline: reading tags, fingerprinting, metadata lookup, audio analysis.
- `crates/` — The AI crate-fill pipeline: SQL filter → vector search → Claude ranking.
- `tests/` — All pytest tests for the backend.
- `watcher.py` — Filesystem watcher that triggers imports when new files appear.

## Running

```bash
uv run uvicorn backend.main:app --reload
```
