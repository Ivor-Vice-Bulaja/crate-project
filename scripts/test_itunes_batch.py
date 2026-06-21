"""
One-off script: run fetch_itunes on the first 50 tracks from a folder,
parsing artist/title from the filename (pattern: "Artist - Title [Label].mp3")
and duration from mutagen.

Results are printed as a summary table and saved to scripts/itunes_batch_results.json.
"""

import json
import re
import sys
from pathlib import Path

import mutagen.mp3

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import ItunesConfig
from backend.importer.itunes import fetch_itunes
from backend.importer.tags import clean_search_title, normalise_artist

FOLDER = Path(r"/mnt/c/Users/Gamer/Desktop/Desktop Temp/JUN2025 - HOUSE TRANCY")
LIMIT = 50
OUTPUT = Path(__file__).parent / "itunes_batch_results.json"

# Filename pattern: "Artist - Title [Label].mp3" or "Artist - Title (Mix) [Label].mp3"
_FILENAME_RE = re.compile(r"^(.+?)\s+-\s+(.+?)(?:\s+\[.*?\])?\s*$")


def parse_filename(stem: str) -> tuple[str, str]:
    m = _FILENAME_RE.match(stem)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # fallback: no hyphen separation found
    return stem, stem


def get_duration(path: Path) -> float | None:
    try:
        f = mutagen.mp3.MP3(str(path))
        return f.info.length
    except Exception:
        return None


def main():
    files = sorted(FOLDER.glob("*.mp3"))[:LIMIT]
    print(f"Running iTunes importer on {len(files)} tracks...\n")

    config = ItunesConfig(rate_limit_delay=3.1, max_search_results=5)
    results = []

    for i, path in enumerate(files, 1):
        artist, title = parse_filename(path.stem)
        artist = normalise_artist(artist)
        title = clean_search_title(title)
        duration = get_duration(path)

        print(f"[{i:02d}/{len(files)}] {artist} — {title}")
        result = fetch_itunes(artist, title, duration, config)

        row = {
            "file": path.name,
            "parsed_artist": artist,
            "parsed_title": title,
            "duration_s": round(duration, 1) if duration else None,
            "confidence": result["itunes_confidence"],
            "matched_artist": result["itunes_artist_name"],
            "matched_title": result["itunes_track_name"],
            "matched_duration_ms": result["itunes_track_time_ms"],
            "release_date": result["itunes_release_date"],
            "genre": result["itunes_genre"],
            "artwork_url": result["itunes_artwork_url"],
            "error": result.get("itunes_error"),
        }
        results.append(row)

        conf = result["itunes_confidence"]
        matched = result["itunes_track_name"] or "-"
        err = result.get("itunes_error") or ""
        print(f"         → [{conf}] {matched}  {err}\n")

    # Summary
    high = sum(1 for r in results if r["confidence"] == "high")
    low = sum(1 for r in results if r["confidence"] == "low")
    none_ = sum(1 for r in results if r["confidence"] == "none")
    errors = sum(1 for r in results if r["error"])

    print("=" * 60)
    print(f"Results: {len(results)} tracks")
    print(f"  high confidence : {high}  ({high/len(results)*100:.0f}%)")
    print(f"  low confidence  : {low}  ({low/len(results)*100:.0f}%)")
    print(f"  no match        : {none_}  ({none_/len(results)*100:.0f}%)")
    print(f"  errors          : {errors}")
    print("=" * 60)

    OUTPUT.write_text(json.dumps(results, indent=2))
    print(f"\nFull results saved to {OUTPUT}")


if __name__ == "__main__":
    main()
