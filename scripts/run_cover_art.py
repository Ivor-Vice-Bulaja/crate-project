"""
run_cover_art.py -- Run Cover Art Archive lookup and print all outputs.

Pass MBIDs directly as arguments:
    .venv/bin/python scripts/run_cover_art.py --release <mbid>
    .venv/bin/python scripts/run_cover_art.py --release-group <mbid>
    .venv/bin/python scripts/run_cover_art.py --release <mbid> --release-group <mbid>
    .venv/bin/python scripts/run_cover_art.py --release <mbid> --no-art
    .venv/bin/python scripts/run_cover_art.py --help

No authentication required — the Cover Art Archive is a public API.
"""

import argparse
import sys

# Force UTF-8 output on Windows (default console codec is cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def fmt_value(value):
    if value is None:
        return "None"
    return str(value)


def print_section(title, keys, result):
    print(f"\n  {title}")
    print(f"  {'─' * len(title)}")
    for key in keys:
        value = result.get(key, "—")
        marker = "  ← ERROR" if key == "cover_art_error" and key in result else ""
        print(f"  {key:<35} {fmt_value(value)}{marker}")


def main():
    parser = argparse.ArgumentParser(
        description="Run Cover Art Archive lookup on a release or release-group MBID and print all outputs."
    )
    parser.add_argument("--release", metavar="MBID", help="MusicBrainz release MBID")
    parser.add_argument(
        "--release-group", metavar="MBID", help="MusicBrainz release-group MBID"
    )
    parser.add_argument(
        "--no-art",
        action="store_true",
        help="Pass mb_has_front_art=False (simulate pre-check skip of release-level call)",
    )
    parser.add_argument(
        "--size",
        type=int,
        choices=[250, 500, 1200],
        default=500,
        help="Thumbnail size to request (default: 500)",
    )
    args = parser.parse_args()

    if not args.release and not args.release_group:
        parser.error("Provide at least one of --release or --release-group")

    from backend.config import CoverArtConfig
    from backend.importer.cover_art import fetch_cover_art

    config = CoverArtConfig(thumbnail_size=args.size)

    mb_has_front_art = False if args.no_art else None

    print(f"\nCover Art Archive lookup")
    print(f"  release MBID:       {args.release or '—'}")
    print(f"  release-group MBID: {args.release_group or '—'}")
    print(f"  thumbnail size:     {args.size}px")
    print(f"  mb_has_front_art:   {mb_has_front_art}")

    result = fetch_cover_art(
        release_mbid=args.release,
        release_group_mbid=args.release_group,
        config=config,
        mb_has_front_art=mb_has_front_art,
    )

    # ── Result ────────────────────────────────────────────────────────────────
    print_section(
        "Result",
        [
            "cover_art_url",
            "cover_art_source",
            "cover_art_lookup_timestamp",
        ],
        result,
    )

    if "cover_art_error" in result:
        print_section("Errors", ["cover_art_error"], result)

    print()

    if result.get("cover_art_url"):
        print(f"  Art found via: {result['cover_art_source']}")
    else:
        print("  No cover art found.")
    print()


if __name__ == "__main__":
    main()
