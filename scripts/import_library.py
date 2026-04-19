"""
import_library.py — CLI entry point for importing a music library into Crate.

Discovers all audio files under a folder, runs move detection to repair stale
file_path values, then drives the import pipeline with a tqdm progress bar.

Usage:
    uv run python scripts/import_library.py --folder /path/to/music
    uv run python scripts/import_library.py --dry-run
"""

import argparse
import hashlib
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import ConfigurationError, PipelineConfig  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.importer.pipeline import import_track  # noqa: E402


def _hash_file(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def discover_files(folder: Path, extensions: set[str]) -> list[Path]:
    paths = [
        p
        for p in folder.rglob("*")
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in extensions
    ]
    return sorted(paths)


def detect_moves(db: sqlite3.Connection, new_paths: list[Path]) -> None:
    """
    For each path not already in the DB, check if its content hash matches an
    existing row at a different path. If exactly one match: update file_path.
    If multiple matches: log a warning and skip.
    """
    logger = logging.getLogger(__name__)

    existing = {row[0] for row in db.execute("SELECT file_path FROM tracks").fetchall()}

    for path in new_paths:
        path_str = str(path)
        if path_str in existing:
            continue

        file_hash = _hash_file(path)
        rows = db.execute(
            "SELECT id, file_path FROM tracks WHERE file_hash = ? AND file_path != ?",
            (file_hash, path_str),
        ).fetchall()

        if len(rows) == 0:
            continue
        elif len(rows) > 1:
            logger.warning(
                "Duplicate hash %s: multiple existing rows match — skipping move update",
                file_hash,
            )
            continue

        old_id, old_path = rows[0][0], rows[0][1]
        new_mtime = str(os.stat(path).st_mtime)
        db.execute(
            "UPDATE tracks SET file_path = ?, file_modified_at = ? WHERE id = ?",
            (path_str, new_mtime, old_id),
        )
        db.commit()
        logger.info("Detected move: %s → %s", old_path, path_str)


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s" if minutes else f"{secs}s"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a music library into Crate.")
    parser.add_argument(
        "--folder",
        default=os.environ.get("MUSIC_FOLDER"),
        help="Path to the music folder (or set MUSIC_FOLDER env var)",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", "./crate.db"),
        help="Path to the SQLite database (default: ./crate.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and count files, then exit without importing",
    )
    parser.add_argument(
        "--extensions",
        default="mp3,flac,wav,aiff,aif",
        help="Comma-separated file extensions to include (default: mp3,flac,wav,aiff,aif)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )

    if not args.folder:
        parser.error(
            "Music folder not set. Pass --folder or set the MUSIC_FOLDER environment variable."
        )

    extensions = {f".{e.strip().lower()}" for e in args.extensions.split(",")}
    folder = Path(args.folder)

    if not folder.is_dir():
        print(f"Error: folder does not exist or is not a directory: {folder}", file=sys.stderr)
        return 1

    paths = discover_files(folder, extensions)
    print(f"Found {len(paths)} audio files")

    if args.dry_run:
        return 0

    if not paths:
        ext_list = ", ".join(e.lstrip(".") for e in sorted(extensions))
        print(
            f"No audio files found in {folder} with extensions: {ext_list}",
            file=sys.stderr,
        )
        return 1

    db = get_db(args.db)
    try:
        detect_moves(db, paths)

        try:
            config = PipelineConfig()
        except ConfigurationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        imported = 0
        skipped = 0
        errors = 0

        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.WARNING)

        start = time.monotonic()

        try:
            from tqdm import tqdm

            with tqdm(total=len(paths), unit="track", dynamic_ncols=True) as bar:
                for path in paths:
                    result = import_track(str(path), db, config)
                    if result is not None:
                        imported += 1
                    else:
                        row = db.execute(
                            "SELECT id FROM tracks WHERE file_path = ?",
                            (str(path),),
                        ).fetchone()
                        if row is not None:
                            skipped += 1
                        else:
                            errors += 1
                    bar.update(1)
                    bar.set_postfix(file=path.name[:40])
        finally:
            root_logger.setLevel(original_level)

        elapsed = time.monotonic() - start

        print(
            f"\nImport complete.\n"
            f"  Imported:  {imported} tracks\n"
            f"  Skipped:   {skipped} (unchanged)\n"
            f"  Errors:    {errors}\n"
            f"  Duration:  {_format_duration(elapsed)}"
        )

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
