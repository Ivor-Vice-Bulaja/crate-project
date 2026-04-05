"""
test_importers.py — Run all current importers on N tracks and print a summary report.

Run from the project root:
    .venv/Scripts/python scripts/test_importers.py
    .venv/Scripts/python scripts/test_importers.py --folder "C:/path/to/music" --count 50
    .venv/Scripts/python scripts/test_importers.py --no-acoustid  # skip AcoustID (fast)
    .venv/Scripts/python scripts/test_importers.py --no-discogs   # skip Discogs
    .venv/Scripts/python scripts/test_importers.py --help

Importers tested:
  1. mutagen  — tag reading
  2. acoustid — AcoustID fingerprinting + MusicBrainz metadata (network, slow ~2s/track)
  3. discogs  — Discogs API enrichment (network, ~1s/track)
  4. cover_art — Cover Art Archive lookup (network, fast)

Requires ACOUSTID_API_KEY, MUSICBRAINZ_APP, DISCOGS_TOKEN in .env or shell.

Outputs:
  - Live progress bar to stdout
  - Summary table to stdout
  - Full JSON results to scripts/output/importers_test_<timestamp>.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 on Windows console (default is cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_FOLDER = Path("C:/Users/bulaj/Desktop/SEP2025")
OUTPUT_DIR = PROJECT_ROOT / "scripts" / "output"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".aiff", ".aif", ".wav", ".m4a", ".ogg"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def collect_tracks(folder: Path, count: int) -> list[Path]:
    """Return up to `count` audio files from `folder`, sorted alphabetically."""
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )
    return files[:count]


def pct(num: int, denom: int) -> str:
    if denom == 0:
        return "n/a"
    return f"{num / denom * 100:.0f}%"


def field_fill_rate(results: list[dict], field: str) -> tuple[int, int]:
    """Return (filled_count, total) for a field across all result dicts."""
    total = len(results)
    filled = sum(
        1 for r in results
        if r.get(field) is not None and r.get(field) != "" and r.get(field) != []
    )
    return filled, total


# ---------------------------------------------------------------------------
# Summary printers
# ---------------------------------------------------------------------------

def print_tags_summary(tag_results: list[dict]) -> None:
    n = len(tag_results)
    errors = sum(1 for r in tag_results if r.get("tags_error"))
    no_tags = sum(1 for r in tag_results if not r.get("tags_present") and not r.get("tags_error"))

    print(f"\n  Tags (mutagen)  — {n} tracks")
    print(f"  {'─' * 40}")
    print(f"  Errors                  {errors:>4}  {pct(errors, n)}")
    print(f"  No tags present         {no_tags:>4}  {pct(no_tags, n)}")

    for label, field in [
        ("title",          "tag_title"),
        ("artist",         "tag_artist"),
        ("album/release",  "tag_album"),
        ("label",          "tag_label"),
        ("catalogue no",   "tag_catalogue_no"),
        ("genre",          "tag_genre"),
        ("BPM",            "tag_bpm"),
        ("key",            "tag_key"),
        ("ISRC",           "tag_isrc"),
        ("year (ID3v2.4)", "tag_year_id3v24"),
        ("year (ID3v2.3)", "tag_year_id3v23"),
        ("cover art",      "has_embedded_art"),
        ("Serato tags",    "has_serato_tags"),
        ("Traktor tags",   "has_traktor_tags"),
        ("Rekordbox tags", "has_rekordbox_tags"),
    ]:
        filled, total = field_fill_rate(tag_results, field)
        # Boolean False counts as "not present" for art/dj-software fields;
        # re-count for those using truthy check.
        if field in ("has_embedded_art", "has_serato_tags", "has_traktor_tags", "has_rekordbox_tags"):
            filled = sum(1 for r in tag_results if r.get(field) is True)
        print(f"  {label:<25} {filled:>4}  {pct(filled, total)}")

    formats = {}
    for r in tag_results:
        fmt = r.get("file_format", "unknown")
        formats[fmt] = formats.get(fmt, 0) + 1
    print(f"\n  Formats: {dict(sorted(formats.items()))}")


def print_acoustid_summary(acoustid_results: list[dict]) -> None:
    n = len(acoustid_results)
    errors = sum(1 for r in acoustid_results if r.get("lookup_error"))
    matches = sum(1 for r in acoustid_results if r.get("acoustid_match") is True)
    has_mb = sum(1 for r in acoustid_results if r.get("mb_recording_id"))
    has_title = sum(1 for r in acoustid_results if r.get("title"))
    has_artist = sum(1 for r in acoustid_results if r.get("artist"))
    has_label = sum(1 for r in acoustid_results if r.get("label"))
    has_year = sum(1 for r in acoustid_results if r.get("year"))
    has_art_flag = sum(1 for r in acoustid_results if r.get("mb_has_front_art") is True)
    scores = [r["acoustid_score"] for r in acoustid_results if r.get("acoustid_score") is not None]

    print(f"\n  AcoustID + MusicBrainz  — {n} tracks")
    print(f"  {'─' * 40}")
    print(f"  Lookup errors           {errors:>4}  {pct(errors, n)}")
    print(f"  AcoustID match          {matches:>4}  {pct(matches, n)}")
    print(f"  Has MB recording ID     {has_mb:>4}  {pct(has_mb, n)}")
    print(f"  Has title (MB)          {has_title:>4}  {pct(has_title, n)}")
    print(f"  Has artist (MB)         {has_artist:>4}  {pct(has_artist, n)}")
    print(f"  Has label (MB)          {has_label:>4}  {pct(has_label, n)}")
    print(f"  Has year (MB)           {has_year:>4}  {pct(has_year, n)}")
    print(f"  Has front art flag      {has_art_flag:>4}  {pct(has_art_flag, n)}")
    if scores:
        print(f"\n  AcoustID score — min={min(scores):.3f}  max={max(scores):.3f}  avg={sum(scores)/len(scores):.3f}")


def print_discogs_summary(discogs_results: list[dict]) -> None:
    n = len(discogs_results)
    errors = sum(1 for r in discogs_results if r.get("discogs_error"))
    high = sum(1 for r in discogs_results if r.get("discogs_confidence") == "high")
    low = sum(1 for r in discogs_results if r.get("discogs_confidence") == "low")
    no_match = sum(1 for r in discogs_results if r.get("discogs_confidence") == "none")

    strategies: dict[str, int] = {}
    for r in discogs_results:
        s = r.get("discogs_search_strategy") or "none"
        strategies[s] = strategies.get(s, 0) + 1

    has_label = sum(1 for r in discogs_results if r.get("discogs_label"))
    has_catno = sum(1 for r in discogs_results if r.get("discogs_catno"))
    has_year = sum(1 for r in discogs_results if r.get("discogs_year"))
    has_genres = sum(
        1 for r in discogs_results
        if r.get("discogs_genres") and r["discogs_genres"] not in ("[]", "null", None)
    )
    has_styles = sum(
        1 for r in discogs_results
        if r.get("discogs_styles") and r["discogs_styles"] not in ("[]", "null", None)
    )

    print(f"\n  Discogs  — {n} tracks")
    print(f"  {'─' * 40}")
    print(f"  Errors                  {errors:>4}  {pct(errors, n)}")
    print(f"  High confidence match   {high:>4}  {pct(high, n)}")
    print(f"  Low confidence match    {low:>4}  {pct(low, n)}")
    print(f"  No match                {no_match:>4}  {pct(no_match, n)}")
    print(f"\n  Search strategies used: {dict(sorted(strategies.items()))}")
    print(f"\n  Has label               {has_label:>4}  {pct(has_label, n)}")
    print(f"  Has catalogue no        {has_catno:>4}  {pct(has_catno, n)}")
    print(f"  Has year                {has_year:>4}  {pct(has_year, n)}")
    print(f"  Has genres              {has_genres:>4}  {pct(has_genres, n)}")
    print(f"  Has styles              {has_styles:>4}  {pct(has_styles, n)}")


def print_essentia_summary(essentia_results: list[dict]) -> None:
    n = len(essentia_results)
    errors = sum(1 for r in essentia_results if r.get("analysis_error"))

    print(f"\n  Essentia  — {n} tracks")
    print(f"  {'─' * 40}")
    print(f"  Errors                  {errors:>4}  {pct(errors, n)}")

    for label, field in [
        ("BPM",                "bpm"),
        ("BPM confidence",     "bpm_confidence"),
        ("key",                "key"),
        ("key strength",       "key_strength"),
        ("integrated loudness","integrated_loudness"),
        ("loudness range",     "loudness_range"),
        ("dynamic complexity", "dynamic_complexity"),
        ("spectral centroid",  "spectral_centroid_hz"),
        ("sub-bass ratio",     "sub_bass_ratio"),
        ("high-freq ratio",    "high_freq_ratio"),
        ("MFCC mean",          "mfcc_mean"),
        ("bark bands",         "bark_bands_mean"),
        ("onset rate",         "onset_rate"),
        ("danceability",       "danceability"),
        ("tuning freq",        "tuning_frequency_hz"),
        ("pitch frames",       "pitch_frames"),
        ("beat ticks",         "beat_ticks"),
        ("genre labels (ML)",  "genre_top_labels"),
        ("embedding (ML)",     "embedding"),
    ]:
        filled, total = field_fill_rate(essentia_results, field)
        print(f"  {label:<25} {filled:>4}  {pct(filled, total)}")

    # BPM stats
    bpms = [r["bpm"] for r in essentia_results if r.get("bpm") is not None]
    if bpms:
        print(f"\n  BPM range: min={min(bpms):.1f}  max={max(bpms):.1f}  avg={sum(bpms)/len(bpms):.1f}")

    # Key distribution
    keys: dict[str, int] = {}
    for r in essentia_results:
        if r.get("key") and r.get("key_scale"):
            k = f"{r['key']} {r['key_scale']}"
            keys[k] = keys.get(k, 0) + 1
    if keys:
        top_keys = sorted(keys.items(), key=lambda x: -x[1])[:6]
        print(f"  Keys (top 6): {dict(top_keys)}")

    # Loudness stats
    loudness = [r["integrated_loudness"] for r in essentia_results if r.get("integrated_loudness") is not None]
    if loudness:
        print(f"  Loudness (LUFS): min={min(loudness):.1f}  max={max(loudness):.1f}  avg={sum(loudness)/len(loudness):.1f}")


def print_cover_art_summary(art_results: list[dict]) -> None:
    n = len(art_results)
    errors = sum(1 for r in art_results if r.get("cover_art_error"))
    has_url = sum(1 for r in art_results if r.get("cover_art_url"))
    from_release = sum(1 for r in art_results if r.get("cover_art_source") == "release")
    from_rg = sum(1 for r in art_results if r.get("cover_art_source") == "release_group")

    print(f"\n  Cover Art Archive  — {n} tracks")
    print(f"  {'─' * 40}")
    print(f"  Network errors          {errors:>4}  {pct(errors, n)}")
    print(f"  Cover art found         {has_url:>4}  {pct(has_url, n)}")
    print(f"    from release          {from_release:>4}  {pct(from_release, n)}")
    print(f"    from release-group    {from_rg:>4}  {pct(from_rg, n)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all importers on N tracks and print a summary report."
    )
    parser.add_argument(
        "--folder",
        default=str(DEFAULT_FOLDER),
        help=f"Folder containing audio files (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of tracks to test (default: 50)",
    )
    parser.add_argument(
        "--no-acoustid",
        action="store_true",
        help="Skip AcoustID + MusicBrainz (no network, fast)",
    )
    parser.add_argument(
        "--no-discogs",
        action="store_true",
        help="Skip Discogs lookup",
    )
    parser.add_argument(
        "--no-cover-art",
        action="store_true",
        help="Skip Cover Art Archive lookup",
    )
    parser.add_argument(
        "--no-rate-limit",
        action="store_true",
        help="Disable MusicBrainz 1s rate limit (use with caution)",
    )
    parser.add_argument(
        "--essentia",
        action="store_true",
        help="Enable Essentia audio analysis (slow: ~30s/track; WSL/Linux only)",
    )
    parser.add_argument(
        "--essentia-count",
        type=int,
        default=10,
        help="Number of tracks to run Essentia on (default: 10; independent of --count)",
    )
    parser.add_argument(
        "--essentia-ml",
        action="store_true",
        help="Enable Essentia ML models (requires model files in ./models/)",
    )
    parser.add_argument(
        "--no-pitch",
        action="store_true",
        help="Disable PredominantPitchMelodia in Essentia (saves ~10–30s/track)",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"ERROR: folder not found: {folder}")
        sys.exit(1)

    tracks = collect_tracks(folder, args.count)
    if not tracks:
        print(f"ERROR: no audio files found in {folder}")
        sys.exit(1)

    n = len(tracks)
    essentia_count = min(args.essentia_count, len(tracks)) if args.essentia else 0

    print(f"\nCrate importer test — {n} tracks from {folder.name}")
    print(f"{'=' * 60}")
    print(f"  mutagen:    always ({n} tracks)")
    print(f"  acoustid:   {'SKIP' if args.no_acoustid else f'enabled (rate-limited) ({n} tracks)'}")
    print(f"  discogs:    {'SKIP' if args.no_discogs else f'enabled ({n} tracks)'}")
    print(f"  cover_art:  {'SKIP' if args.no_cover_art else f'enabled ({n} tracks)'}")
    print(f"  essentia:   {'enabled (no ML, no pitch)' if args.essentia and not args.essentia_ml and args.no_pitch else 'enabled (no ML)' if args.essentia and not args.essentia_ml else 'enabled (full)' if args.essentia else 'SKIP'}{f' ({essentia_count} tracks)' if args.essentia else ''}")
    print()

    # --- Lazy imports (only import what we'll use) ---
    from backend.importer.tags import read_tags

    acoustid_fn = None
    acoustid_config = None
    if not args.no_acoustid:
        try:
            from backend.importer.acoustid import identify_track
            from backend.config import AcoustIDConfig
            acoustid_config = AcoustIDConfig(mb_rate_limit=not args.no_rate_limit)
            acoustid_fn = identify_track
        except Exception as exc:
            print(f"  WARNING: could not load acoustid module: {exc}")
            print("  Skipping AcoustID.\n")

    discogs_client_obj = None
    discogs_config = None
    discogs_fn = None
    if not args.no_discogs:
        try:
            import discogs_client as dc
            from backend.importer.discogs import fetch_discogs_metadata
            from backend.config import DiscogsConfig
            discogs_config = DiscogsConfig()
            discogs_client_obj = dc.Client(
                discogs_config.user_agent,
                user_token=discogs_config.discogs_token or None,
            )
            discogs_fn = fetch_discogs_metadata
        except Exception as exc:
            print(f"  WARNING: could not load discogs module: {exc}")
            print("  Skipping Discogs.\n")

    cover_art_fn = None
    cover_art_config = None
    if not args.no_cover_art:
        try:
            from backend.importer.cover_art import fetch_cover_art
            from backend.config import CoverArtConfig
            cover_art_config = CoverArtConfig()
            cover_art_fn = fetch_cover_art
        except Exception as exc:
            print(f"  WARNING: could not load cover_art module: {exc}")
            print("  Skipping cover art.\n")

    essentia_fn = None
    essentia_config = None
    if args.essentia:
        try:
            from backend.importer.essentia_analysis import analyse_track
            from backend.config import EssentiaConfig
            essentia_config = EssentiaConfig(
                run_ml_models=args.essentia_ml,
                run_pitch_analysis=not args.no_pitch,
            )
            essentia_fn = analyse_track
        except Exception as exc:
            print(f"  WARNING: could not load essentia module: {exc}")
            print("  Skipping Essentia.\n")

    # --- Run importers ---
    all_results: list[dict] = []
    tag_results: list[dict] = []
    acoustid_results: list[dict] = []
    discogs_results: list[dict] = []
    art_results: list[dict] = []
    essentia_results: list[dict] = []

    t_start = time.time()

    for i, track_path in enumerate(tracks, 1):
        track_name = track_path.name
        # Truncate for display
        display_name = track_name[:55] + "…" if len(track_name) > 56 else track_name
        print(f"  [{i:>2}/{n}] {display_name}", end="\r", flush=True)

        row: dict = {"file_path": str(track_path), "file_name": track_name}

        # 1. Tags
        tags = read_tags(str(track_path))
        row["tags"] = tags
        tag_results.append(tags)

        # 2. AcoustID + MusicBrainz
        if acoustid_fn and acoustid_config:
            aid = acoustid_fn(str(track_path), acoustid_config)
            row["acoustid"] = aid
            acoustid_results.append(aid)
        else:
            row["acoustid"] = None

        # 3. Discogs — prefer MB-derived metadata, fall back to tags
        if discogs_fn and discogs_client_obj and discogs_config:
            mb = row.get("acoustid") or {}
            artist = mb.get("artist") or tags.get("tag_artist")
            title = mb.get("title") or tags.get("tag_title")
            catno = tags.get("tag_catalogue_no") or mb.get("catalogue_number")
            year = mb.get("year")
            # barcode: not available from tags (ID3 has no standard barcode field)
            disc = discogs_fn(
                artist=artist,
                title=title,
                catno=catno,
                barcode=None,
                year=year,
                client=discogs_client_obj,
                config=discogs_config,
            )
            row["discogs"] = disc
            discogs_results.append(disc)
        else:
            row["discogs"] = None

        # 4. Cover Art Archive
        if cover_art_fn and cover_art_config:
            mb = row.get("acoustid") or {}
            art = cover_art_fn(
                release_mbid=mb.get("mb_release_id"),
                release_group_mbid=mb.get("mb_release_group_id"),
                config=cover_art_config,
                mb_has_front_art=mb.get("mb_has_front_art"),
            )
            row["cover_art"] = art
            art_results.append(art)
        else:
            row["cover_art"] = None

        # 5. Essentia — only for the first essentia_count tracks
        if essentia_fn and essentia_config and i <= essentia_count:
            ess = essentia_fn(str(track_path), essentia_config)
            row["essentia"] = ess
            essentia_results.append(ess)
        else:
            row["essentia"] = None

        all_results.append(row)

    elapsed = time.time() - t_start

    # Clear progress line
    print(f"  {' ' * 70}", end="\r")
    print(f"  Done — {n} tracks in {elapsed:.1f}s ({elapsed / n:.1f}s/track avg)")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")

    print_tags_summary(tag_results)

    if acoustid_results:
        print_acoustid_summary(acoustid_results)
    else:
        print("\n  AcoustID + MusicBrainz  — skipped")

    if discogs_results:
        print_discogs_summary(discogs_results)
    else:
        print("\n  Discogs  — skipped")

    if art_results:
        print_cover_art_summary(art_results)
    else:
        print("\n  Cover Art Archive  — skipped")

    if essentia_results:
        print_essentia_summary(essentia_results)
    else:
        print("\n  Essentia  — skipped")

    print()

    # --- Spot-check: first 5 tracks with MB + Discogs data ---
    matched = [
        r for r in all_results
        if r.get("acoustid") and r["acoustid"].get("acoustid_match")
    ]
    if matched:
        print(f"{'=' * 60}")
        print(f"  SPOT-CHECK — first {min(5, len(matched))} AcoustID matches")
        print(f"{'=' * 60}")
        for r in matched[:5]:
            t = r["tags"]
            mb = r["acoustid"]
            d = r.get("discogs") or {}
            art = r.get("cover_art") or {}
            print(f"\n  File    : {r['file_name'][:70]}")
            print(f"  Tag     : {t.get('tag_artist')} — {t.get('tag_title')}")
            print(f"  MB      : {mb.get('artist')} — {mb.get('title')} ({mb.get('year')})")
            print(f"  Label   : MB={mb.get('label') or '—'}  Discogs={d.get('discogs_label') or '—'}")
            print(f"  Catno   : MB={mb.get('catalogue_number') or '—'}  Discogs={d.get('discogs_catno') or '—'}")
            print(f"  Styles  : {d.get('discogs_styles') or '—'}")
            print(f"  Art     : {art.get('cover_art_url') or 'none'} ({art.get('cover_art_source') or 'none'})")
        print()

    # --- Save JSON ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = OUTPUT_DIR / f"importers_test_{ts}.json"

    # Make results JSON-serialisable (convert Path objects etc.)
    def serialise(obj):
        if isinstance(obj, Path):
            return str(obj)
        # mutagen ID3TimeStamp and similar objects that have a str() representation
        try:
            return str(obj)
        except Exception:
            raise TypeError(f"Not serialisable: {type(obj)}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=serialise, ensure_ascii=False)

    print(f"  Full results saved to: {out_path.relative_to(PROJECT_ROOT)}")
    print()


if __name__ == "__main__":
    main()
