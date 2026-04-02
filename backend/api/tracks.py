"""
GET /tracks — returns the track library with optional filter, sort, and group params.
Not yet implemented — Phase 3.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("")
def get_tracks() -> list:
    """Return all tracks. Filters and sorting to be added in Phase 3."""
    return []
