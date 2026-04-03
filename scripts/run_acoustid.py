"""
run_acoustid.py -- Run AcoustID + MusicBrainz lookup on an audio file and print all outputs.

Run from the project root in WSL:
    .venv/bin/python scripts/run_acoustid.py "Cevi - High Line.wav"
    .venv/bin/python scripts/run_acoustid.py "Cevi - High Line.wav" --no-label
    .venv/bin/python scripts/run_acoustid.py "Cevi - High Line.wav" --no-rate-limit
    .venv/bin/python scripts/run_acoustid.py --help

Requires ACOUSTID_API_KEY and MUSICBRAINZ_APP in .env (or shell environment).
"""

import argparse
import os
import sys
from pathlib import Path


def fmt_value(value):
    """Format a result value for readable display."""
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def print_section(title, keys, result):
    print(f"\n  {title}")
    print(f"  {'─' * len(title)}")
    for key in keys:
        value = result.get(key, "—")
        marker = ""
        if key == "lookup_error":
            marker = "  ← ERROR"
        print(f"  {key:<35} {fmt_value(value)}{marker}")


def main():
    parser = argparse.ArgumentParser(
        description="Run AcoustID fingerprinting + MusicBrainz lookup on a track and print all outputs."
    )
    parser.add_argument("file", help="Path to the audio file")
    parser.add_argument(
        "--no-label",
        action="store_true",
        help="Skip the second MusicBrainz call for label/catalogue number",
    )
    parser.add_argument(
        "--no-rate-limit",
        action="store_true",
        help="Disable 1 req/s sleep before MusicBrainz calls (faster, may hit 503)",
    )
    args = parser.parse_args()

    # Resolve the file path — handles both relative and absolute paths
    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = Path(os.getcwd()) / file_path
    file_path = file_path.resolve()

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    from backend.config import AcoustIDConfig
    from backend.importer.acoustid import identify_track

    config = AcoustIDConfig(
        fetch_label=not args.no_label,
        mb_rate_limit=not args.no_rate_limit,
    )

    print(f"\nLooking up: {file_path.name}")
    print(f"  Label lookup:   {'disabled' if args.no_label else 'enabled'}")
    print(f"  MB rate limit:  {'disabled' if args.no_rate_limit else 'enabled'}")
    print()

    result = identify_track(str(file_path), config)

    if "lookup_error" in result:
        print(f"\nLOOKUP FAILED: {result['lookup_error']}")
        sys.exit(1)

    # ── AcoustID ──────────────────────────────────────────────────────────────
    print_section(
        "AcoustID",
        [
            "acoustid_match",
            "acoustid_id",
            "acoustid_score",
        ],
        result,
    )

    # ── MusicBrainz IDs ───────────────────────────────────────────────────────
    print_section(
        "MusicBrainz IDs",
        [
            "mb_recording_id",
            "mb_release_id",
            "mb_artist_id",
        ],
        result,
    )

    # ── Track metadata ────────────────────────────────────────────────────────
    print_section(
        "Track metadata",
        [
            "title",
            "artist",
            "artist_sort_name",
            "year",
            "mb_duration_s",
            "isrc",
        ],
        result,
    )

    # ── Release ───────────────────────────────────────────────────────────────
    print_section(
        "Release",
        [
            "mb_release_title",
            "mb_release_group_type",
            "release_status",
            "release_country",
            "label",
            "catalogue_number",
        ],
        result,
    )

    # ── Tags & genres ─────────────────────────────────────────────────────────
    print_section(
        "Tags & genres",
        [
            "genres",
            "tags",
        ],
        result,
    )

    print()


if __name__ == "__main__":
    main()
