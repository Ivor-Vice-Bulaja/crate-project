# Implementation Plan: scripts/import_library.py

## Overview

`import_library.py` is the CLI entry point for a full library import. It discovers
all audio files under a given folder, opens the SQLite database (running migrations
once), runs a move-detection pass to repair stale `file_path` values before the
pipeline sees them, constructs a single `PipelineConfig`, then drives
`import_tracks()` with a tqdm progress bar. The script is responsible only for
discovery, DB setup, move detection, config, progress display, and summary output.
All per-track logic — hashing, importer calls, DB writes, error handling — is
delegated entirely to `pipeline.py`.

---

## CLI Interface

Use `argparse.ArgumentParser` with the following arguments:

| Flag | Type | Default | Notes |
|---|---|---|---|
| `--folder` | `str` | `os.environ.get("MUSIC_FOLDER")` | Required if env var unset; error with clear message |
| `--db` | `str` | `os.environ.get("DB_PATH", "./crate.db")` | Path to SQLite file |
| `--dry-run` | `store_true` | `False` | Discover + count files, print count, exit 0 |
| `--extensions` | `str` | `"mp3,flac,wav,aiff,aif"` | Comma-separated; parsed to lowercase set |
| `--log-level` | `str` | `"INFO"` | Passed to `logging.basicConfig` |

**Validation:**

```python
args = parser.parse_args()
if not args.folder:
    parser.error(
        "Music folder not set. Pass --folder or set the MUSIC_FOLDER environment variable."
    )
```

`parser.error()` prints the message and exits with code 2 (argparse convention).

No flags for individual importer toggles. Those knobs live in `PipelineConfig`
fields which are set via env vars.

---

## File Discovery

```python
def discover_files(folder: Path, extensions: set[str]) -> list[Path]:
    paths = [
        p for p in folder.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and p.suffix.lower() in extensions
    ]
    return sorted(paths)
```

- Use `Path.rglob("*")`, not `os.walk`.
- Filter with `.suffix.lower() in extensions` where `extensions` is a set built from
  the `--extensions` argument: `{f".{e.strip()}" for e in args.extensions.split(",")}`.
  The leading dot is prepended here so the comparison matches `Path.suffix` directly.
- Symlinks to files are skipped via `not p.is_symlink()`. A symlink's target could be
  outside the library root; skipping avoids ambiguity and duplicate imports.
- Sort the result with `sorted(paths)` so repeated runs process files in the same
  stable alphabetical order — important for predictable progress output and
  reproducible debugging.
- Print count before import starts:
  ```
  Found 4823 audio files
  ```

---

## File Path Stability (Move Detection)

### Problem

The database uses `file_path` as the unique key (UNIQUE constraint, primary lookup
for `_check_skip`). If a file moves from `House/Track.mp3` to `Techno/Track.mp3`,
the pipeline's `_check_skip` finds no row for the new path and treats it as a new
file — inserting a duplicate row and leaving the old row as a dead record.

### Detection algorithm

Move detection runs **after** full file discovery and **before** `import_tracks()`,
so the complete set of new paths is known. It does not run migrations — that must
happen first, as a separate step.

For each discovered path that is **not already in the database** (no row for that
`file_path`):

1. Compute the file's MD5 hash using the same chunked algorithm as `pipeline._hash_file`:
   ```python
   def _hash_file(path: Path, chunk_size: int = 65536) -> str:
       h = hashlib.md5()
       with open(path, "rb") as f:
           while chunk := f.read(chunk_size):
               h.update(chunk)
       return h.hexdigest()
   ```
2. Query the database for any existing row with a matching `file_hash` but a
   different `file_path`:
   ```sql
   SELECT id, file_path FROM tracks WHERE file_hash = ? AND file_path != ?
   ```
3. If exactly **one** row matches:
   - Compute the new path's `mtime` with `os.stat(path).st_mtime`.
   - Update the stored path and mtime so the pipeline's mtime fast-path fires
     correctly on the next run:
     ```sql
     UPDATE tracks SET file_path = ?, file_modified_at = ? WHERE id = ?
     ```
   - Log at INFO level:
     ```
     INFO Detected move: House/Track.mp3 → Techno/Track.mp3
     ```
4. If **zero** rows match: it is a genuinely new file — do nothing, let the pipeline
   import it normally.
5. If **two or more** rows match the same hash: there are duplicate files in the
   library. Skip the update and log a WARNING:
   ```
   WARNING Duplicate hash {hash}: multiple existing rows match — skipping move update
   ```

### `vec_tracks` note

`vec_tracks` rows are keyed on `track_id` (the integer primary key of `tracks`),
not on `file_path`. Because move detection only updates `file_path` in the `tracks`
row — the `id` primary key is unchanged — the `vec_tracks` embedding row remains
valid and requires no update.

### Performance note

Move detection hashes only files that are **not already in the database**. On the
first run this is all files; on subsequent runs (most files already imported) it is
only new arrivals. Hashing is O(file size) but only runs when needed.

---

## Progress Display

tqdm lives entirely in this script. `pipeline.py` only calls the `on_progress`
callback; the script decides how to render it.

```python
from tqdm import tqdm

with tqdm(total=len(paths), unit="track", dynamic_ncols=True) as bar:
    def on_progress(done: int, total: int, path: str) -> None:
        bar.update(1)
        bar.set_postfix(file=Path(path).name[:40])

    import_tracks(paths, db, config, on_progress=on_progress)
```

The `on_progress` callback signature matches `pipeline.import_tracks` exactly:
`on_progress(done: int, total: int, path: str)`. The `done` and `total` parameters
are available if needed for display but `bar.update(1)` is sufficient — tqdm tracks
its own internal count.

**Logger suppression during the tqdm run:** per-track INFO lines from importers will
bleed through the tqdm bar and corrupt its display. Suppress them for the duration
of the import:

```python
root_logger = logging.getLogger()
original_level = root_logger.level
root_logger.setLevel(logging.WARNING)
try:
    import_tracks(paths, db, config, on_progress=on_progress)
finally:
    root_logger.setLevel(original_level)
```

This applies to all loggers (pipeline, acoustid, discogs, etc.). Restore the
original level in `finally` so post-import summary logging works normally.

---

## Summary Report

### Counter design

`import_tracks()` does not return counters. `on_progress` receives `(done, total,
path)` — no outcome information. The distinction between skip and error is not
available from the callback alone.

**Solution:** wrap `import_track` via a closure that captures return values into
mutable counters. Because `import_tracks` calls `import_track` internally, the
counter wrapper must be applied at the `import_track` level by monkey-patching
or by duplicating the batch loop. The cleaner approach is to **re-implement the
batch loop in the script** (it is four lines in `pipeline.py`) rather than
monkey-patching:

```python
imported = 0
skipped = 0
errors = 0

with tqdm(total=len(paths), unit="track", dynamic_ncols=True) as bar:
    for i, path in enumerate(paths, 1):
        result = import_track(str(path), db, config)
        if result is not None:
            imported += 1
        else:
            # Distinguish skip from error:
            # _check_skip is called first in import_track. If the file was in
            # the DB unchanged, the pipeline logs at DEBUG and returns None
            # immediately — no importer ran, no error logged.
            # If an importer raised (or the DB write failed), the pipeline
            # logs at ERROR and returns None after partial work.
            # The script cannot distinguish these from outside the pipeline.
            #
            # Practical resolution: query the DB to see if the row exists.
            # If a row exists for this file_path, it was a skip (existing
            # unchanged track). If no row exists, something failed.
            row = db.execute(
                "SELECT id FROM tracks WHERE file_path = ?", (str(path),)
            ).fetchone()
            if row is not None:
                skipped += 1
            else:
                errors += 1
        bar.update(1)
        bar.set_postfix(file=Path(path).name[:40])
```

This re-implements the four-line batch loop directly in the script, giving full
visibility into per-track outcomes without modifying `pipeline.py`.

### Output format

```
Import complete.
  Imported:  4823 tracks
  Skipped:   177 (unchanged)
  Errors:    0
  Duration:  4m 32s
```

Duration is measured with `time.monotonic()`:

```python
start = time.monotonic()
# ... import loop ...
elapsed = time.monotonic() - start
minutes, seconds = divmod(int(elapsed), 60)
duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
```

---

## Database Setup

```python
from backend.database import get_db

db = get_db(args.db)
try:
    # move detection, import loop, summary
finally:
    db.close()
```

`get_db()` already:
- Calls `sqlite3.connect()`
- Sets `row_factory = sqlite3.Row` (confirmed in `_configure_connection`)
- Sets `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`
- Loads sqlite-vec if available
- Runs all pending migrations

The script must not run migrations itself. Migrations run exactly once inside
`get_db()`, before both move detection and `import_tracks()`.

---

## PipelineConfig Construction

Construct one instance before the import loop — not one per track:

```python
try:
    config = PipelineConfig()
except ConfigurationError as exc:
    print(f"Error: {exc}", file=sys.stderr)
    return 1
```

`PipelineConfig.__post_init__` calls `AcoustIDConfig()` and the Discogs client
constructor. `AcoustIDConfig` calls `_require("ACOUSTID_API_KEY")` and
`_require("MUSICBRAINZ_APP")` — if either is missing a `ConfigurationError` is
raised at instantiation. No manual field assignment is needed in this script.

The script does not need to check `ACOUSTID_API_KEY` or `MUSICBRAINZ_APP`
separately — `PipelineConfig()` does it. The script only needs to catch the
exception and print a clear message before exiting:

```
Error: Required environment variable 'ACOUSTID_API_KEY' is not set. Copy .env.example to .env and fill in your values.
```

Exit code 1 for config errors.

---

## Logging Setup

```python
logging.basicConfig(
    level=getattr(logging, args.log_level.upper(), logging.INFO),
    format="%(levelname)s %(name)s %(message)s",
)
```

Call this at the top of `main()`, before `get_db()`, `PipelineConfig()`, or any
other call that may trigger logging. The `getattr` with fallback handles invalid
`--log-level` values gracefully.

During the tqdm run, the root logger level is raised to WARNING (see Progress
Display section). It is restored to the user's chosen level in a `finally` block
after the import loop completes.

---

## Entry Point

```python
def main() -> int:
    # parse args, setup logging, open DB, move detection, import, summary
    return 0  # or 1 on error

if __name__ == "__main__":
    sys.exit(main())
```

- `main()` returns an integer exit code: `0` = success, `1` = config error or no
  files found.
- No top-level side effects outside `if __name__ == "__main__"` — the script is
  safe to import from tests without triggering any I/O.
- For the no-files case, print a clear message and return 1:
  ```
  No audio files found in /path/to/folder with extensions: mp3, flac, wav, aiff, aif
  ```

---

## Test Plan

All tests live in `backend/tests/test_importer/test_import_library.py`. No live
network calls in any test — all importers are mocked unless stated otherwise.

### Discovery test

Set up a `tmp_path` directory containing `track.mp3`, `track.flac`, `notes.txt`,
and `cover.jpg`. Call `discover_files(tmp_path, {".mp3", ".flac"})`. Assert the
returned list contains exactly the two audio paths, in sorted order, and excludes
the `.txt` and `.jpg` files.

Create a subdirectory with another `.mp3` file inside it. Assert `discover_files`
finds it too (confirms `rglob` recursion works).

Create a symlink pointing to a `.mp3` file. Assert it is **not** returned (confirms
symlink skip).

### Dry-run test

Mock `import_tracks` (or `import_track`) with `unittest.mock.patch`. Call
`main(["--folder", str(tmp_path), "--dry-run"])` with a folder containing two
`.mp3` files. Assert the mock was never called. Assert the script printed the
discovered file count and exited with code 0.

### Move detection test

Open an in-memory SQLite connection via `get_db(":memory:")`. Insert a row into
`tracks` with a known `file_hash` and a `file_path` that does not exist on disk
(e.g. `"old/path.mp3"`). Create a new temp file with the same content (so its MD5
matches). Call `detect_moves(db, [new_path])` (the extracted helper function).
Assert the DB row's `file_path` has been updated to the new path. Assert the
`file_modified_at` in the row matches the actual mtime of the new file.

### Duplicate hash test

Open an in-memory SQLite connection. Insert **two** rows with the same
`file_hash` but different `file_path` values. Create a new temp file with the
same content. Call `detect_moves(db, [new_path])`. Assert neither row's `file_path`
was changed. Use `caplog` or `unittest.mock` to assert a WARNING was logged
containing "Duplicate hash".

### Progress counter test

Open an in-memory SQLite connection (schema applied via `get_db(":memory:")`). Mock
`import_track` to return a dict for the first two paths (simulating successful
import) and `None` for the third (simulating a skip — pre-insert a row for that
path so the script's DB query classifies it as "skipped"). Mock `import_track` to
return `None` for the fourth path without inserting a row (simulating an error).
Call the script's import loop directly. Assert `imported == 2`, `skipped == 1`,
`errors == 1`.

### Config error test

Temporarily unset `ACOUSTID_API_KEY` from the environment using
`monkeypatch.delenv("ACOUSTID_API_KEY", raising=False)`. Call
`main(["--folder", str(tmp_path)])` and capture stderr. Assert the exit code is 1.
Assert the output contains the expected error message about the missing key.

---

## Implementation Order

1. **Scaffold the script file** — create `scripts/import_library.py` with the
   `main()` function stub, `if __name__` guard, and `sys.exit(main())`. Confirm it
   is importable without side effects.

2. **Implement `discover_files()`** — rglob, extension filter, symlink skip, sort.
   Write the discovery test first; confirm it passes before continuing.

3. **Implement CLI argument parsing** — all five flags with defaults and the
   folder-not-set validation. Confirm `--help` output looks correct.

4. **Implement logging setup** — `logging.basicConfig` call at the top of `main()`.

5. **Implement DB open and close** — `get_db(args.db)` with `try/finally` close.
   Confirm the connection opens against a temp file in a quick manual test.

6. **Implement `PipelineConfig` construction with error handling** — `try/except
   ConfigurationError`, print message, return 1. Write the config error test.

7. **Implement `detect_moves(db, paths)`** as a standalone function — hash loop,
   SELECT query, UPDATE, logging. Write the move detection test and duplicate hash
   test before integrating it into `main()`.

8. **Implement the import loop with counters** — the four-line loop with
   `import_track`, result check, DB query for skip/error classification. Write the
   progress counter test.

9. **Wire tqdm** — wrap the import loop in a `tqdm` context manager, add the
   `on_progress` callback, add the logger suppression block.

10. **Implement summary report** — duration measurement with `time.monotonic()`,
    formatted output block. Confirm output format matches spec.

11. **Implement `--dry-run`** — call `discover_files`, print count, return 0
    immediately. Write the dry-run test.

12. **End-to-end smoke test** — run the script manually against a small sample
    folder (5–10 tracks) via WSL2, confirm the tqdm bar displays correctly, summary
    counts are accurate, and the DB is populated.
