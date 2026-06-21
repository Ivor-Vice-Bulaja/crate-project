"""
test_pipeline.py — Run the full import pipeline on a single file and print results.

Usage:
    uv run python scripts/test_pipeline.py "Cevi - High Line.wav"
    uv run python scripts/test_pipeline.py  # defaults to the WAV in project root
"""

import logging
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
)

from backend.config import PipelineConfig  # noqa: E402
from backend.database import init_db  # noqa: E402
from backend.importer.pipeline import import_track  # noqa: E402


def main():
    project_root = Path(__file__).parent.parent

    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if not file_path.is_absolute():
            file_path = project_root / file_path
    else:
        # Default to the WAV in the project root
        wavs = list(project_root.glob("*.wav"))
        if not wavs:
            print("No WAV file found in project root. Pass a path as an argument.")
            sys.exit(1)
        file_path = wavs[0]

    print(f"\n=== Pipeline test: {file_path.name} ===\n")

    # Use an in-memory DB so this is non-destructive
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_db(db)

    config = PipelineConfig()

    def progress(stage):
        print(f"  [{stage}]")

    result = import_track(file_path, db, config, progress_callback=progress)

    if result is None:
        print("\nPipeline returned None (error or skip).")
        sys.exit(1)

    # Print a summary of what was resolved
    print("\n--- Resolved fields ---")
    resolved_keys = [k for k in result if k.startswith("resolved_")]
    for k in resolved_keys:
        print(f"  {k}: {result[k]}")

    print("\n--- Source matches ---")
    print(
        f"  AcoustID match:     {result.get('acoustid_match')}  (score: {result.get('acoustid_score')})"
    )
    print(f"  MB recording ID:    {result.get('mb_recording_id')}")
    print(
        f"  Discogs release ID: {result.get('discogs_release_id')}  (strategy: {result.get('discogs_search_strategy')})"
    )
    print(
        f"  iTunes track ID:    {result.get('itunes_track_id')}  (strategy: {result.get('itunes_search_strategy')})"
    )
    print(f"  CAA URL:            {result.get('caa_url')}")

    print("\n--- Audio features (Essentia) ---")
    es_keys = [k for k in result if k.startswith("es_") and result[k] is not None]
    for k in sorted(es_keys):
        v = result[k]
        # Truncate long JSON arrays
        if isinstance(v, str) and len(v) > 80:
            v = v[:77] + "..."
        print(f"  {k}: {v}")

    print("\n--- Tag data ---")
    tag_keys = [
        "tag_title",
        "tag_artist",
        "tag_album",
        "tag_label",
        "tag_bpm",
        "tag_key",
        "tag_genre",
        "tag_year_id3v24",
        "tag_duration_seconds",
        "tag_file_format",
    ]
    for k in tag_keys:
        v = result.get(k)
        if v is not None:
            print(f"  {k}: {v}")

    print()


if __name__ == "__main__":
    main()
