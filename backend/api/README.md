# backend/api/

FastAPI route handlers. One file per resource group.

## What belongs here

- `tracks.py` — `GET /tracks` with filter, sort, and group parameters
- `crates.py` — CRUD endpoints for crates + the fill endpoint (`POST /crates/{id}/fill`)
- `search.py` — Natural language search endpoint (`POST /search`)

Each file defines an `APIRouter` that is registered in `main.py`.
