"""
run_discogs.py -- Run Discogs API lookup and print all outputs.

Pass track metadata directly as arguments:
    .venv/bin/python scripts/run_discogs.py --catno "PM-020"
    .venv/bin/python scripts/run_discogs.py --artist "Jeff Mills" --title "The Bells" --year 1997
    .venv/bin/python scripts/run_discogs.py --catno "PM-020" --artist "Jeff Mills" --year 1997
    .venv/bin/python scripts/run_discogs.py --barcode "042284224321"
    .venv/bin/python scripts/run_discogs.py --catno "PM-020" --fetch-master
    .venv/bin/python scripts/run_discogs.py --help

Requires DISCOGS_TOKEN in .env (or shell environment).
Without a token the script falls back to unauthenticated mode (25 req/min).
"""

import argparse
import json
import sys

# Force UTF-8 output on Windows (default console codec is cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


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


def fmt_json(value):
    """Pretty-print a JSON string field, or return it as-is if not valid JSON."""
    if value is None:
        return "None"
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            if not parsed:
                return "[]"
            return "[" + ", ".join(str(v) for v in parsed) + "]"
        return str(parsed)
    except (json.JSONDecodeError, TypeError):
        return str(value)


def print_section(title, keys, result, json_keys=None):
    json_keys = json_keys or set()
    print(f"\n  {title}")
    print(f"  {'─' * len(title)}")
    for key in keys:
        value = result.get(key, "—")
        if key in json_keys:
            display = fmt_json(value)
        else:
            display = fmt_value(value)
        print(f"  {key:<40} {display}")


def print_tracklist(result):
    raw = result.get("discogs_tracklist")
    if not raw:
        print("\n  Tracklist")
        print("  ─────────")
        print("  (none)")
        return

    try:
        tracks = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        print("\n  Tracklist")
        print("  ─────────")
        print(f"  {raw}")
        return

    print(f"\n  Tracklist ({len(tracks)} tracks)")
    print("  " + "─" * 20)
    for t in tracks:
        pos = t.get("position") or ""
        title = t.get("title") or ""
        dur = t.get("duration") or ""
        print(f"  {pos:<6} {title:<40} {dur}")


def print_extraartists_raw(result):
    raw = result.get("discogs_extraartists_raw")
    if not raw:
        return
    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return
    if not entries:
        return
    print("\n  Extra artists (raw)")
    print("  " + "─" * 19)
    for e in entries:
        name = e.get("name") or ""
        role = e.get("role") or ""
        print(f"  {name:<30} {role}")


def main():
    parser = argparse.ArgumentParser(
        description="Run Discogs API lookup for a track and print all outputs."
    )
    parser.add_argument("--artist", default=None, help="Artist name")
    parser.add_argument("--title", default=None, help="Track or release title")
    parser.add_argument("--label", default=None, help="Label name (from file tags)")
    parser.add_argument("--catno", default=None, help="Catalogue number")
    parser.add_argument("--barcode", default=None, help="Barcode")
    parser.add_argument("--year", type=int, default=None, help="Release year")
    parser.add_argument(
        "--fetch-master",
        action="store_true",
        help="Make an extra call to fetch the master release (adds master_year etc.)",
    )
    parser.add_argument(
        "--no-vinyl-filter",
        action="store_true",
        help="Disable the Vinyl format filter on the first artist+title search attempt",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Max candidates to score per search call (default: 5, max: 10)",
    )
    args = parser.parse_args()

    if not any([args.artist, args.title, args.label, args.catno, args.barcode]):
        parser.error("Provide at least one of: --artist, --title, --catno, --barcode")

    import discogs_client

    from backend.config import DiscogsConfig

    config = DiscogsConfig(
        fetch_master=args.fetch_master,
        vinyl_filter_first=not args.no_vinyl_filter,
        max_search_results=min(args.max_results, 10),
    )

    if not config.discogs_token:
        print("  Note: DISCOGS_TOKEN not set — running unauthenticated (25 req/min)")

    client = discogs_client.Client(
        config.user_agent,
        user_token=config.discogs_token,
    )

    print(f"\nSearching Discogs for:")
    print(f"  artist:  {args.artist or '—'}")
    print(f"  title:   {args.title or '—'}")
    print(f"  label:   {args.label or '—'}")
    print(f"  catno:   {args.catno or '—'}")
    print(f"  barcode: {args.barcode or '—'}")
    print(f"  year:    {args.year or '—'}")
    print(f"  fetch_master:   {config.fetch_master}")
    print(f"  vinyl_filter:   {config.vinyl_filter_first}")
    print()

    from backend.importer.discogs import fetch_discogs_metadata

    result = fetch_discogs_metadata(
        artist=args.artist,
        title=args.title,
        label=args.label,
        catno=args.catno,
        barcode=args.barcode,
        year=args.year,
        client=client,
        config=config,
    )

    # ── Match summary ─────────────────────────────────────────────────────────
    confidence = result.get("discogs_confidence", "none")
    strategy = result.get("discogs_search_strategy", "none")
    error = result.get("discogs_error")

    if error:
        print(f"  LOOKUP FAILED: {error}")
        sys.exit(1)

    if confidence == "none":
        print("  No match found.")
        print(f"  discogs_lookup_timestamp  {result.get('discogs_lookup_timestamp')}")
        sys.exit(0)

    confidence_label = {"high": "HIGH ✓", "low": "LOW — review recommended"}.get(
        confidence, confidence
    )
    print_section(
        "Match",
        [
            "discogs_confidence",
            "discogs_search_strategy",
            "discogs_release_id",
            "discogs_url",
            "discogs_lookup_timestamp",
        ],
        {**result, "discogs_confidence": confidence_label},
    )

    # ── Release ───────────────────────────────────────────────────────────────
    print_section(
        "Release",
        [
            "discogs_title",
            "discogs_year",
            "discogs_country",
            "discogs_released",
            "discogs_released_formatted",
            "discogs_status",
            "discogs_data_quality",
            "discogs_notes",
        ],
        result,
    )

    # ── Label ─────────────────────────────────────────────────────────────────
    print_section(
        "Label",
        [
            "discogs_label",
            "discogs_catno",
            "discogs_label_id",
            "discogs_label_entity_type",
        ],
        result,
    )

    # ── Artists ───────────────────────────────────────────────────────────────
    print_section(
        "Artists",
        [
            "discogs_artists",
            "discogs_artists_sort",
        ],
        result,
        json_keys={"discogs_artists"},
    )

    # ── Genres & styles ───────────────────────────────────────────────────────
    print_section(
        "Genres & styles",
        [
            "discogs_genres",
            "discogs_styles",
        ],
        result,
        json_keys={"discogs_genres", "discogs_styles"},
    )

    # ── Formats ───────────────────────────────────────────────────────────────
    print_section(
        "Formats",
        [
            "discogs_format_names",
            "discogs_format_descs",
        ],
        result,
        json_keys={"discogs_format_names", "discogs_format_descs"},
    )

    # ── Credits ───────────────────────────────────────────────────────────────
    print_section(
        "Credits",
        [
            "discogs_producers",
            "discogs_remixers",
        ],
        result,
        json_keys={"discogs_producers", "discogs_remixers"},
    )
    print_extraartists_raw(result)

    # ── Marketplace ───────────────────────────────────────────────────────────
    print_section(
        "Marketplace",
        [
            "discogs_have",
            "discogs_want",
            "discogs_rating_avg",
            "discogs_rating_count",
            "discogs_num_for_sale",
            "discogs_lowest_price",
        ],
        result,
    )

    # ── Identifiers ───────────────────────────────────────────────────────────
    print_section(
        "Identifiers",
        [
            "discogs_barcodes",
            "discogs_matrix_numbers",
        ],
        result,
        json_keys={"discogs_barcodes", "discogs_matrix_numbers"},
    )

    # ── Master ────────────────────────────────────────────────────────────────
    print_section(
        "Master release",
        [
            "discogs_master_id",
            "discogs_master_url",
            "discogs_master_year",
            "discogs_master_most_recent_id",
        ],
        result,
    )

    # ── Tracklist ─────────────────────────────────────────────────────────────
    print_tracklist(result)

    print()


if __name__ == "__main__":
    main()
