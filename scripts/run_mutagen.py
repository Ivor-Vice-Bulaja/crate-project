"""
run_mutagen.py -- Run mutagen tag extraction on an audio file and print all outputs.

Run from the project root:
    .venv/bin/python scripts/run_mutagen.py "Cevi - High Line.wav"
    .venv/bin/python scripts/run_mutagen.py --help

Accepts MP3, FLAC, AIFF, WAV, M4A, OGG.
"""

import argparse
import os
import sys
from pathlib import Path


def fmt_value(value):
    """Format a result value for readable display."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def print_section(title, keys, result):
    print(f"\n  {title}")
    print(f"  {'-' * len(title)}")
    for key in keys:
        value = result.get(key, "—")
        marker = ""
        if key == "tags_error" and value not in (None, "None"):
            marker = "  <-- ERROR"
        print(f"  {key:<35} {fmt_value(value)}{marker}")


def main():
    parser = argparse.ArgumentParser(
        description="Run mutagen tag extraction on an audio file and print all outputs."
    )
    parser.add_argument("file", help="Path to the audio file")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = Path(os.getcwd()) / file_path
    file_path = file_path.resolve()

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    from backend.importer.tags import read_tags

    print(f"\nReading tags: {file_path.name}")
    print()

    result = read_tags(str(file_path))

    # ── File identity & status ────────────────────────────────────────────────
    print_section(
        "File identity & status",
        ["file_path", "file_format", "tag_format_type", "tags_present", "tags_error"],
        result,
    )

    # ── Audio stream properties ───────────────────────────────────────────────
    print_section(
        "Audio stream",
        [
            "duration_seconds",
            "bitrate_bps",
            "bitrate_mode",
            "sample_rate_hz",
            "channels",
            "bits_per_sample",
            "encoder_info",
            "is_sketchy",
        ],
        result,
    )

    # ── Core text fields ──────────────────────────────────────────────────────
    print_section(
        "Core text fields",
        [
            "tag_title",
            "tag_artist",
            "tag_album_artist",
            "tag_album",
            "tag_label",
            "tag_catalogue_no",
            "tag_genre",
            "tag_comment",
            "tag_isrc",
            "tag_copyright",
        ],
        result,
    )

    # ── Date / year ───────────────────────────────────────────────────────────
    print_section(
        "Date / year",
        [
            "tag_year_id3v24",
            "tag_year_id3v23",
            "tag_date_released",
            "tag_date_original",
            "tag_date_vorbis",
            "tag_date_mp4",
        ],
        result,
    )

    # ── Track / disc numbering ────────────────────────────────────────────────
    print_section(
        "Track / disc numbering",
        ["tag_track_number", "tag_disc_number"],
        result,
    )

    # ── DJ-relevant fields ────────────────────────────────────────────────────
    print_section(
        "DJ-relevant fields",
        ["tag_bpm", "tag_key", "tag_initial_key_txxx", "tag_energy"],
        result,
    )

    # ── Cover art & DJ software ───────────────────────────────────────────────
    print_section(
        "Cover art & DJ software",
        [
            "has_embedded_art",
            "has_serato_tags",
            "has_traktor_tags",
            "has_rekordbox_tags",
            "tag_id3_version",
        ],
        result,
    )

    print()


if __name__ == "__main__":
    main()
