"""
Crate — FastAPI application entry point.

Start the server with:
    uv run uvicorn backend.main:app --reload
"""

from fastapi import FastAPI

from backend.api import tracks

app = FastAPI(title="Crate", version="0.1.0")

app.include_router(tracks.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Routers registered here as they are built:
# from backend.api import crates, search
# app.include_router(crates.router)
# app.include_router(search.router)
