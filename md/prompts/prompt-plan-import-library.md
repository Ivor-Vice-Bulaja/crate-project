# Task: Plan `scripts/import_library.py`

## Context

Read `CLAUDE.md` and `CURRENT_STATE.md` before starting. This is a planning task —
no code is written here. The output is a detailed implementation plan for
`scripts/import_library.py`.

Read the following files in full before writing the plan:

- `backend/importer/pipeline.py` — public API: `import_track()`, `import_tracks()`,
  and the `on_progress` callback signature
- `backend/config.py` — `PipelineConfig`, `Settings`, and how env vars are loaded
- `backend/database.py` — `get_db()` interface, migration runner, `_VEC_AVAILABLE`

---

## What this script does

`import_library.py` is the command-line entry point for importing a music library.
It:

1. Discovers all audio files in the music folder (recursively)
2. Opens the SQLite database and runs migrations
3. Constructs a `PipelineConfig`
4. Calls `import_tracks()` with a tqdm progress bar
5. Prints a summary at the end

The pipeline (`import_tracks`) already handles per-track logic, skipping,
concurrency, and errors. This script is only responsible for discovery, DB setup,
config, and progress display.

---

## What to plan

### 1. CLI interface

Design the argument parser using `argparse`.

Specify:
- `--folder` — path to the music folder; defaults to `MUSIC_FOLDER` env var;
  error clearly if neither is set
- `--db` — path to the SQLite database; defaults to `DB_PATH` env var
  (which defaults to `./crate.db`)
- `--dry-run` — discover and count files, print the count, then exit without
  importing anything
- `--extensions` — comma-separated list of file extensions to include;
  default: `mp3,flac,wav,aiff,aif`
- `--log-level` — override logging level; default: `INFO`
- No other flags; do not add options for individual importer toggles (those live
  in `PipelineConfig` fields)

### 2. File discovery

Specify:
- Use `pathlib.Path.rglob("*")` for recursive discovery — do not use `os.walk`
- Filter by extension using a lowercase set comparison
  (`.suffix.lower() in extensions_set`)
- Sort the result before passing to `import_tracks()` so that repeated runs
  process files in a stable, predictable order
- Print the discovered count before starting: `Found 4823 audio files`
- Whether to resolve symlinks or skip them (skip — a symlink to a file is
  ambiguous in a local-first library)

### 3. File path stability

**Core requirement:** the library must not lose data when files are moved or
renamed. The database uses `file_path` as the unique key for each track. If a file
moves from `House/Track.mp3` to `Techno/Track.mp3`, the pipeline currently treats
it as a brand new file and inserts a duplicate row, leaving the old row as a dead
record.

Design a move-detection strategy that runs before `import_tracks()`:

- For each discovered file that is **not** already in the database, compute its
  MD5 hash (same algorithm as `_hash_file` in `pipeline.py`: chunked, 65536 bytes)
- Query the database for any existing row with a matching `file_hash` but a
  different `file_path`
- If a match is found, `UPDATE tracks SET file_path = ? WHERE file_hash = ?`
  to update the stored path before the pipeline runs
- The pipeline's hash-check step will then find the row unchanged and skip it —
  no re-import, no data loss, no duplicate
- Log each detected move at `INFO` level:
  `Detected move: old/path.mp3 → new/path.mp3`
- If more than one existing row matches the same hash (duplicate files in the
  library), skip the update and log a `WARNING` — do not guess which is correct

Specify:
- Whether move detection runs before or after the full discovery scan
  (it must run after — we need the full list of new paths first)
- The exact SQL query to find a hash match with a different path:
  `SELECT id, file_path FROM tracks WHERE file_hash = ? AND file_path != ?`
- The exact SQL update:
  `UPDATE tracks SET file_path = ?, file_modified_at = ? WHERE id = ?`
  (update `file_modified_at` to current mtime of the new path so the pipeline's
  mtime fast-path fires correctly on future runs)
- Whether the `vec_tracks` embedding row (keyed on `track_id`, not `file_path`)
  needs updating — it does not; `track_id` is stable across moves

### 4. Progress display

Specify:
- Use `tqdm` with `total=len(paths)`, `unit="track"`, `dynamic_ncols=True`
- The `on_progress` callback passed to `import_tracks()` updates the tqdm bar
  by calling `bar.update(1)` and `bar.set_postfix(file=Path(path).name[:40])`
- tqdm lives in this script, not in `pipeline.py` — the pipeline only calls the
  callback; the script decides what to do with it
- Do not print per-track log lines at INFO during the import run — they clutter
  the progress bar; set the pipeline logger to WARNING during batch import,
  then restore it after

### 5. Summary report

After `import_tracks()` returns, print a summary to stdout:

```
Import complete.
  Imported:  4823 tracks
  Skipped:   177 (unchanged)
  Errors:    0
  Duration:  4m 32s
```

Specify:
- Count "imported" as tracks where `import_track()` returned a dict (not None)
- Count "skipped" as tracks where `import_track()` returned None due to hash hit
  (not error)
- Count "errors" as tracks where `import_track()` returned None due to an
  exception (the pipeline logs the error; the script counts it)
- The pipeline's `on_progress` callback receives `(done, total, path)` — use this
  to increment counters; the distinction between skip and error is not in the
  callback signature; propose how to track this (e.g. count returned dicts vs None
  in a wrapper around `import_track`)
- Duration: `time.monotonic()` before and after the loop

### 6. Database setup

Specify:
- Call `get_db(db_path)` from `backend/database.py` — this opens the connection
  and runs migrations
- The `row_factory = sqlite3.Row` must be set on the connection (confirm whether
  `get_db()` already does this)
- Close the connection in a `finally` block after the import completes
- Do not run migrations inside the move-detection step — run migrations once, before
  both move detection and `import_tracks()`

### 7. PipelineConfig construction

Specify:
- Construct one `PipelineConfig()` instance before the import loop — not one per
  track
- `PipelineConfig` reads env vars via its dataclass defaults; no manual field
  assignment needed in this script
- If `ACOUSTID_API_KEY` is missing, `PipelineConfig()` will raise
  `ConfigurationError` — catch it, print a clear message, and exit with code 1:
  ```
  Error: ACOUSTID_API_KEY is not set. Copy .env.example to .env and fill in your values.
  ```
- Same for `MUSICBRAINZ_APP`

### 8. Logging setup

Specify:
- Call `logging.basicConfig(level=log_level, format="%(levelname)s %(name)s %(message)s")`
  at startup — before any imports that trigger logging
- During the tqdm progress run, set the root logger level to WARNING so INFO lines
  do not bleed through the bar; restore to the user's chosen level after

### 9. Entry point and import guard

Specify:
- The script ends with `if __name__ == "__main__": main()`
- No top-level side effects outside of `if __name__` — safe to import from tests
- The `main()` function returns an exit code (0 = success, 1 = config error or
  no files found); call `sys.exit(main())`

### 10. Test plan

Describe the tests for `backend/tests/test_importer/test_import_library.py`.

- **Discovery test:** create a temp directory with a mix of `.mp3`, `.txt`, and
  `.jpg` files; assert only the `.mp3` paths are returned
- **Dry-run test:** assert `import_tracks()` is never called when `--dry-run` is
  passed
- **Move detection test:** insert a row into a real SQLite DB with a known hash and
  a path that does not exist on disk; create a file with the same content at a
  different path; run move detection; assert the DB row's `file_path` is updated to
  the new path
- **Duplicate hash test:** insert two rows with the same hash but different paths;
  run move detection; assert neither row's path is changed and a WARNING is logged
- **Progress counter test:** mock `import_track()` to return a dict for some calls
  and None for others; assert the summary counts are correct
- **Config error test:** unset `ACOUSTID_API_KEY`; assert the script exits with
  code 1 and prints the expected error message
- No live network calls in any test

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/plan-import-library.md
```

Structure:

```
# Implementation Plan: scripts/import_library.py

## Overview
One paragraph: what the script does, what it delegates, what it guarantees.

## CLI Interface
argparse setup. All flags with defaults and validation.

## File Discovery
rglob pattern. Extension filter. Sort. Symlink handling.

## File Path Stability (Move Detection)
Problem statement. Detection algorithm. SQL queries. vec_tracks note.
Edge cases (duplicate hashes).

## Progress Display
tqdm setup. on_progress callback wiring. Logger suppression during run.

## Summary Report
Counter design. Duration measurement. Output format.

## Database Setup
get_db() call. Migration timing. Connection lifecycle.

## PipelineConfig Construction
Single instance. ConfigurationError handling. Exit codes.

## Logging Setup
basicConfig call. Level suppression during tqdm run.

## Entry Point
main() signature. if __name__ guard. sys.exit.

## Test Plan
One paragraph per test with: what it sets up, what it calls, what it asserts.

## Implementation Order
Numbered steps.
```

---

## Definition of done

- [ ] `md/plans/plan-import-library.md` exists
- [ ] All three source files listed above have been read before writing the plan
- [ ] Move detection section includes exact SQL queries (SELECT and UPDATE)
- [ ] Move detection covers the duplicate hash edge case
- [ ] tqdm placement is specified as the calling script, not `pipeline.py`
- [ ] Progress callback wiring matches the `on_progress(done, total, path)`
      signature from `pipeline.py`
- [ ] Summary report explains how skip vs error is distinguished given the
      callback signature
- [ ] `PipelineConfig` construction addresses `ConfigurationError` with an exit code
- [ ] Logger suppression during the tqdm run is specified
- [ ] Test plan covers move detection, duplicate hash, dry-run, and config error
- [ ] No design decisions are left vague
- [ ] Implementation order is a concrete numbered list of buildable steps
