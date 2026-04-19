# Import Pipeline Research

_Phase 2 research for `backend/importer/pipeline.py`. Written 2026-04-19._

---

## Sources

- [concurrent.futures — Python 3 docs](https://docs.python.org/3/library/concurrent.futures.html)
- [logging — Python 3 docs](https://docs.python.org/3/library/logging.html)
- [Logging Cookbook — Python 3 docs](https://docs.python.org/3/howto/logging-cookbook.html)
- [hashlib — Python 3 docs](https://docs.python.org/3/library/hashlib.html)
- [SQLite Autoincrement](https://sqlite.org/autoinc.html)
- [SQLite Foreign Key Support](https://sqlite.org/foreignkeys.html)
- [Dexter's log — INSERT ON CONFLICT REPLACE with ON DELETE CASCADE](https://dexterslog.com/posts/insert-on-conflict-replace-with-on-delete-cascade-in-sqlite/)
- [sqlite-vec Python docs — Alex Garcia](https://alexgarcia.xyz/sqlite-vec/python.html)
- [sqlite-vec simple-python demo](https://github.com/asg017/sqlite-vec/blob/main/examples/simple-python/demo.py)
- [Upsert into vec0 tables? — sqlite-vec issue #127](https://github.com/asg017/sqlite-vec/issues/127)
- [scivision/detect-windows-subsystem-for-linux](https://github.com/scivision/detect-windows-subsystem-for-linux)
- [mtime comparison considered harmful — apenwarr](https://apenwarr.ca/log/20181113)

---

## Concurrency Design

### Decision: ThreadPoolExecutor, not asyncio

All six importers are **synchronous blocking functions**. Running them under asyncio would require wrapping every call in `loop.run_in_executor()`, which adds complexity with no benefit — asyncio's value is in native `async/await` code that can yield without blocking. For a pipeline that calls six synchronous library functions, `ThreadPoolExecutor` is the correct tool.

`ThreadPoolExecutor` is safe for all network I/O workloads in this pipeline. The GIL is released during blocking I/O syscalls (socket reads/writes), so threads genuinely run concurrently for `identify_track()`, `fetch_itunes()`, `fetch_cover_art()`, and `fetch_discogs_metadata()`. For `analyse_track()` (CPU-bound Essentia), the GIL is also released by C extensions during computation — Essentia is a C++ library wrapped in Python.

### Import

```python
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from concurrent.futures import TimeoutError as FuturesTimeoutError
```

### submit() vs map()

Use `submit()`. `map()` requires homogeneous callables with the same argument shape; the six importers have completely different signatures. `submit(fn, *args)` returns a `Future` object per call, which is exactly what we need to associate results back to their importer names.

```python
with ThreadPoolExecutor(max_workers=3) as executor:
    fut_acoustid = executor.submit(identify_track, path, acoustid_config)
    fut_itunes   = executor.submit(fetch_itunes, artist, title, duration, itunes_config)
    fut_essentia = executor.submit(analyse_track, path, essentia_config)
```

### Retrieving results

```python
acoustid_result = fut_acoustid.result(timeout=60)
```

- `future.result()` blocks until the future completes and returns the callable's return value.
- If the callable **raised an exception**, `.result()` re-raises it in the calling thread.
- `timeout=N` (int or float): raises `concurrent.futures.TimeoutError` if the result isn't ready within N seconds. **The timed-out thread continues running in the background** — it is not cancelled. For a pipeline that never raises (all importers return dicts), this is safe; the thread will eventually finish and its result will be discarded.

### Exception propagation

All six importers are designed to **never raise** — they catch all exceptions internally and return a dict with an error key. This means `.result()` will never raise in normal operation. However, defensive code should still wrap `.result()` in a try/except to guard against unexpected bugs.

```python
try:
    result = future.result(timeout=60)
except FuturesTimeoutError:
    logger.warning("Importer timed out after 60s: %s", importer_name)
    result = {}
except Exception as exc:
    logger.error("Importer raised unexpectedly: %s — %s", importer_name, exc)
    result = {}
```

### Context manager and exception safety

```python
with ThreadPoolExecutor(max_workers=3) as executor:
    ...
```

When the `with` block exits (either normally or via exception), the executor calls `shutdown(wait=True)`, which **blocks until all pending futures complete**. Futures already submitted are **not cancelled** — they run to completion. This guarantees no orphaned threads when the pipeline function returns.

### Execution order for this pipeline

The dependency chain (from CLAUDE.md) maps to this concrete sequence:

```
Step 1:  hash_check()                      — synchronous, fast
Step 2:  read_tags(path)                   — synchronous, instant

Step 3:  ThreadPoolExecutor(max_workers=3):
           fut_acoustid = submit(identify_track, path, acoustid_cfg)
           fut_itunes   = submit(fetch_itunes, artist, title, duration, itunes_cfg)
           fut_essentia = submit(analyse_track, path, essentia_cfg)  # skipped if not WSL2

         acoustid_result = fut_acoustid.result(timeout=90)  # AcoustID + up to 2 MB calls
         itunes_result   = fut_itunes.result(timeout=30)
         essentia_result = fut_essentia.result(timeout=300) if fut_essentia else {}

Step 4:  fetch_discogs_metadata(...)        — synchronous, uses tags + acoustid results
Step 5:  fetch_cover_art(...)              — synchronous, uses acoustid results

Step 6:  Compute resolved_* fields
Step 7:  INSERT ... ON CONFLICT DO UPDATE  — single write
Step 8:  (separate) vec_tracks upsert      — DELETE then INSERT
```

**Timeout values rationale:**
- AcoustID + MusicBrainz: up to 3 sequential network calls with 1s rate-limit sleep between each. 90s is generous.
- iTunes: single HTTP call with 3s rate-limit delay and up to 3 country fallbacks. 30s is sufficient.
- Essentia: CPU-bound, 5–30s per track for standard analysis. 300s covers ML models on long tracks.

### asyncio — why not

To run synchronous importers under asyncio you must call `loop.run_in_executor(None, fn, *args)` for each, which internally uses a `ThreadPoolExecutor` anyway. You get all the complexity of asyncio with none of the benefit. Asyncio would only be appropriate if the importers were rewritten as `async def` coroutines — not planned.

---

## File Hashing and Change Detection

### Algorithm choice

Use **MD5**. The skip-check needs fast change detection, not collision resistance — it is not a security mechanism. MD5 is the fastest widely-available hashlib algorithm on common hardware (roughly 2–4× faster than SHA-256). For a 300 MB FLAC file, chunked MD5 takes ~0.5s vs ~1.5s for SHA-256.

SHA-1 is a reasonable alternative (faster than SHA-256, slower than MD5) but offers nothing over MD5 for this use case.

### Chunked hashing — exact pattern

Never read the whole file into memory. Files are 50–500 MB.

```python
import hashlib

def hash_file(path: str, chunk_size: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

`65536` bytes (64 KB) is the recommended chunk size — large enough to minimise Python loop overhead, small enough to avoid memory pressure. The walrus operator (`:=`) requires Python 3.8+; the codebase already targets 3.11+.

### mtime reliability

`os.stat().st_mtime` returns a float (Unix timestamp, sub-second precision available on most filesystems).

**Windows NTFS (native Python):** Reliable. NTFS records modification time with 100-nanosecond precision. `st_mtime` is accurate.

**WSL2 mounts of Windows paths (`/mnt/c/...`):** The WSL2 kernel translates NTFS timestamps via the DrvFs filesystem driver. Precision is preserved in practice, but there is a known edge case: copying a file with a tool that explicitly preserves timestamps may produce an mtime identical to the original source. For this reason, **mtime alone is not sufficient** — hash comparison is required as the second check.

**The skip logic:**

```python
# Skip the track if hash AND mtime both match the stored values.
# Hash change = content changed.
# mtime change with same hash = file metadata touched but content unchanged (safe to skip).
stored = conn.execute(
    "SELECT file_hash, file_modified_at FROM tracks WHERE file_path = ?",
    (path,)
).fetchone()

if stored:
    current_mtime = str(os.stat(path).st_mtime)
    if stored["file_hash"] is not None and stored["file_modified_at"] == current_mtime:
        # Fast path: mtime unchanged → very likely unchanged. Still verify hash.
        current_hash = hash_file(path)
        if current_hash == stored["file_hash"]:
            return  # skip
```

Alternatively, check mtime first (cheap), hash only if mtime changed. This avoids hashing unchanged files on every run:

```python
if stored and stored["file_modified_at"] == current_mtime:
    return  # mtime unchanged — skip without hashing
# mtime changed or no stored record — hash and proceed
```

The latter is acceptable when Essentia has not been run yet (the pipeline will re-import the track to add Essentia data regardless). For a general-purpose skip check, always verifying hash when mtime differs is safer.

### Storing mtime in SQLite

Store as a **TEXT column** containing the float representation: `str(os.stat(path).st_mtime)`. This is already the schema in `database.py` (`file_modified_at TEXT`). Using a string avoids float-to-integer truncation in SQLite's type affinity system and round-trips exactly.

---

## SQLite Insert Strategy

### INSERT OR REPLACE is wrong for this schema

`INSERT OR REPLACE` is implemented as **DELETE then INSERT**. It:
1. Deletes the conflicting row (the existing track row).
2. Inserts a new row with a **new AUTOINCREMENT id**.
3. The new id is guaranteed to be higher than any previously used id (AUTOINCREMENT semantics).

This breaks the foreign key relationships in `crate_tracks` and `crate_corrections`, which reference `tracks(id)`. Even though those tables use `ON DELETE CASCADE`, the cascade **deletes all crate memberships** for the track on every re-import. That is data loss.

Confirmed from [sqlite.org forum](https://sqlite.org/forum/info/98d4fb9ced866287) and [Dexter's log](https://dexterslog.com/posts/insert-on-conflict-replace-with-on-delete-cascade-in-sqlite/): "REPLACE is implemented as delete then insert" and "ON DELETE CASCADE will delete your records."

### Recommendation: UPSERT (`INSERT ... ON CONFLICT DO UPDATE SET`)

SQLite 3.24.0 (2018-06-04) introduced UPSERT. All current Python environments ship SQLite ≥ 3.35. The minimum required version for this project is not specified, but 3.24 is safely below any Python 3.11+ installation.

UPSERT **never deletes the existing row** — it performs an in-place update, preserving the existing `id`. Foreign keys in `crate_tracks` and `crate_corrections` remain valid.

**Exact SQL pattern:**

```sql
INSERT INTO tracks (
    file_path,
    file_hash,
    file_size_bytes,
    file_modified_at,
    -- ... all other columns ...
    imported_at
)
VALUES (
    :file_path,
    :file_hash,
    :file_size_bytes,
    :file_modified_at,
    -- ... all other values ...
    :imported_at
)
ON CONFLICT(file_path) DO UPDATE SET
    file_hash           = excluded.file_hash,
    file_size_bytes     = excluded.file_size_bytes,
    file_modified_at    = excluded.file_modified_at,
    -- ... all columns except id and file_path ...
    imported_at         = excluded.imported_at;
```

`excluded` is a special table alias that refers to the values that would have been inserted. The `id` column is **not** listed in the UPDATE SET clause — it keeps its original value.

`file_path` is the conflict target because it has a `UNIQUE` constraint (`UNIQUE INDEX idx_tracks_file_path`).

### INSERT OR IGNORE + UPDATE — when appropriate

This pattern is useful when you want to avoid touching existing rows unless explicitly requested. It is more code (two statements), harder to read, and provides no benefit over UPSERT for this pipeline. Not recommended.

---

## Partial Results and Error Isolation

### Design

Every importer already returns a dict and never raises. The pipeline must:

1. Call all importers even if earlier ones fail.
2. Merge all dicts into a single `track_data` dict.
3. Write the merged dict to the database regardless of how many importers returned empty/error dicts.
4. Log per-importer failures with the file path context.

```python
importer_results = {}
for name, future in futures.items():
    try:
        importer_results[name] = future.result(timeout=TIMEOUT_MAP[name])
    except FuturesTimeoutError:
        logger.warning("[%s] %s timed out", path, name)
        importer_results[name] = {}
    except Exception as exc:
        logger.error("[%s] %s raised unexpectedly: %s", path, name, exc)
        importer_results[name] = {}

track_data = {}
for result in importer_results.values():
    track_data.update(result)
```

### Logging pattern

Use `logging.LoggerAdapter` to inject `file_path` into every log line from inside the pipeline function, without passing it to every helper.

```python
import logging

class _TrackLogger(logging.LoggerAdapter):
    """Prepends the track path to every log message."""
    def process(self, msg, kwargs):
        return f"[{self.extra['path']}] {msg}", kwargs

logger = logging.getLogger(__name__)

def import_track(path: str, ...) -> None:
    tlog = _TrackLogger(logger, {"path": path})
    tlog.info("Starting import")
    tlog.warning("AcoustID timed out")
```

### Per-module loggers — standard convention

The Python convention is **one logger per module**, named `logging.getLogger(__name__)`. All six importers already follow this (confirmed by reading each file). The pipeline module adds its own `logger = logging.getLogger(__name__)`. The root logger or application-level handler controls the output format — individual modules don't set handlers or formatters.

---

## Essentia Availability Detection

### Why detection is needed

Essentia's Python bindings do not work on native Windows. On WSL2, `import essentia` works. When the pipeline runs from native Windows Python (the normal dev/prod path for this project's FastAPI backend), `import essentia` will either fail with `ImportError` or — if essentia-tensorflow is somehow installed — fail at runtime when algorithms try to run.

The current `essentia_analysis.py` already guards with `try: import essentia.standard as _es_check` at module load — confirming that import can succeed or fail. The pipeline needs to make the skip decision before calling `analyse_track()`.

### Detection method: read `/proc/version`

```python
import os

def _is_wsl2() -> bool:
    """Return True if running inside WSL2."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False
```

On native Windows (where `/proc` does not exist), `open("/proc/version")` raises `OSError` → returns False.
On WSL2, `/proc/version` contains a string like `Linux version 5.15.90.1-microsoft-standard-WSL2`.
On native Linux, `/proc/version` exists but does not contain "microsoft" → returns False (correct).

This is the most reliable method. `platform.release()` also works on WSL2 (returns `"5.15.90.1-microsoft-standard-WSL2"`) but `sys.platform` always returns `"linux"` inside WSL2, making it useless for WSL vs native Linux distinction.

**Is `try: import essentia` sufficient?** Not reliably. Essentia can be installed in a virtual environment that is also accessible from Windows paths via the WSL filesystem mount. Additionally, the native Windows essentia package may in the future provide Windows binaries. The `/proc/version` check is more explicit and stable.

### Making the skip visible once, not per-track

```python
_ESSENTIA_AVAILABLE = _is_wsl2()

if not _ESSENTIA_AVAILABLE:
    logger.info(
        "Essentia analysis disabled: not running in WSL2. "
        "Re-run from WSL2 to enable audio feature extraction."
    )
```

Log at module import time (once per process start). Inside `import_track()`, simply pass `None` as the essentia result if `_ESSENTIA_AVAILABLE` is False — no per-track log needed.

---

## Progress Reporting

### Options evaluated

| Pattern | Pros | Cons |
|---|---|---|
| `callable` progress callback | Simple, no dependencies | Caller must be thread-safe if callback touches UI |
| `queue.Queue` | Thread-safe, decouples producer/consumer | Caller must drain the queue |
| Generator / `yield` | Natural for CLI `tqdm` integration | Incompatible with `ThreadPoolExecutor` unless wrapped |
| Return count from batch function | Zero plumbing | No per-track granularity |

### Recommendation: optional progress callback

```python
from typing import Callable

def import_tracks(
    paths: list[str],
    ...,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> None:
    total = len(paths)
    for i, path in enumerate(paths):
        import_track(path, ...)
        if on_progress:
            on_progress(i + 1, total, path)
```

`on_progress(done, total, current_path)` is called after each track completes. The callback runs in the main thread (not in the executor threads), so it is safe to update `tqdm` or a FastAPI progress counter from it.

### tqdm integration — keep it in the calling script

`tqdm` belongs in CLI scripts and test harnesses, not in `pipeline.py`. The library function should not import `tqdm`.

```python
# In scripts/import_library.py — not in pipeline.py
from tqdm import tqdm

with tqdm(total=len(paths)) as pbar:
    def on_progress(done, total, path):
        pbar.set_postfix_str(Path(path).name)
        pbar.update(1)

    import_tracks(paths, ..., on_progress=on_progress)
```

---

## Config Object Design

### Current pattern in config.py

`config.py` uses **`@dataclass`** with `field(default_factory=...)` for values that read from environment variables. There is one dataclass per importer:

| Config class | Used by |
|---|---|
| `EssentiaConfig` | `analyse_track()` |
| `AcoustIDConfig` | `identify_track()` |
| `DiscogsConfig` | `fetch_discogs_metadata()` |
| `ItunesConfig` | `fetch_itunes()` |
| `CoverArtConfig` | `fetch_cover_art()` |

`tags.py` has no config object — it takes only a path.

`Settings` (the global singleton) holds API keys and paths; each per-importer dataclass reads from environment variables via `_require()` / `_optional()` in its `field(default_factory=...)`.

### Recommendation: single PipelineConfig wrapping per-importer configs

```python
@dataclass
class PipelineConfig:
    acoustid: AcoustIDConfig = field(default_factory=AcoustIDConfig)
    discogs: DiscogsConfig   = field(default_factory=DiscogsConfig)
    itunes: ItunesConfig     = field(default_factory=ItunesConfig)
    cover_art: CoverArtConfig = field(default_factory=CoverArtConfig)
    essentia: EssentiaConfig  = field(default_factory=EssentiaConfig)
    max_workers: int = 3
    skip_essentia: bool = False  # set True automatically if not WSL2
```

Callers construct `PipelineConfig()` and pass it to `import_track()`. Individual importer configs are accessible as attributes. This avoids a function signature with six config arguments.

### dataclasses vs pydantic

`dataclasses` is the right choice here. Reasons:
- Already used throughout `config.py` — consistency.
- No runtime validation needed: the pipeline doesn't receive untrusted external data; configs are internal Python objects set at startup.
- No JSON serialisation/deserialisation needed.
- Zero extra dependencies.

Pydantic adds value when validating external data (HTTP request bodies, config files). For internal config objects constructed in Python code, it is overkill.

### Environment variable loading

Environment variables are already loaded by `config.py` via `load_dotenv()` at module import time. The `_require()` / `_optional()` helpers handle reading. This should stay in `config.py` — not scattered into `pipeline.py` or individual importers.

---

## Embedding Generation

### When resolved fields are available

Resolved fields (`resolved_title`, `resolved_artist`, `resolved_label`, `resolved_year`) can only be computed **after all importers have returned and the merge is complete**. The embedding text string (e.g. `"artist - title label year"`) therefore depends on the merge step.

### Where to compute embeddings

Embeddings should be computed **inside `pipeline.py` after the merge step**, not in a separate embeddings.py call invoked later. Reasons:
- The resolved fields needed to generate the embedding text are only available inside `import_track()`.
- Separating embeddings into a second pass would require re-reading every track's metadata from the database to reconstruct the text, which is wasteful.
- The vec_tracks row should be created/updated atomically with the tracks row (same import event).

The embedding model (sentence-transformers) is CPU-bound but fast for a single track (~10–50 ms). It does not need to be in the ThreadPoolExecutor pool — call it synchronously after the merge step.

### sqlite-vec insert syntax

**Table definition (already in database.py):**

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS vec_tracks USING vec0(
    track_id  INTEGER PRIMARY KEY,
    embedding FLOAT[1280] distance_metric=cosine
);
```

**Python serialisation:**

```python
from sqlite_vec import serialize_float32
import numpy as np

# embedding is a list[float] or np.ndarray from sentence-transformers
if isinstance(embedding, np.ndarray):
    vec_bytes = embedding.astype(np.float32).tobytes()
else:
    vec_bytes = serialize_float32(embedding)  # equivalent to struct.pack(...)
```

`serialize_float32(vector)` is equivalent to `struct.pack(f"{len(vector)}f", *vector)`.
NumPy arrays can be passed as `.astype(np.float32).tobytes()` directly (Buffer protocol).

**Insert syntax — no UPSERT on vec0:**

From [sqlite-vec issue #127](https://github.com/asg017/sqlite-vec/issues/127): `UPSERT not implemented for virtual table`. The `ON CONFLICT DO UPDATE` syntax raises an error on vec0 tables.

The correct approach is **DELETE then INSERT**:

```python
conn.execute("DELETE FROM vec_tracks WHERE track_id = ?", (track_id,))
conn.execute(
    "INSERT INTO vec_tracks(track_id, embedding) VALUES (?, ?)",
    (track_id, vec_bytes),
)
```

This must be called **after** the `tracks` UPSERT commits (so that `track_id` is known and valid), using the `id` returned from the tracks insert:

```python
cursor = conn.execute("SELECT id FROM tracks WHERE file_path = ?", (path,))
track_id = cursor.fetchone()["id"]
```

Or using `lastrowid` — but this is unreliable with UPSERT (an update, not an insert, does not set `lastrowid`). Always use the SELECT to get `track_id`.

---

## Resolved Field Logic

### Fallback chain implementation pattern

`next((v for v in [a, b, c] if v), None)` is correct for most fields. It skips `None` **and** empty strings (`""` is falsy in Python). This is the desired behaviour: an empty string tag is treated as absent.

For `resolved_year`, the sources may be strings that need slicing. Use a helper:

```python
def _year_from(value) -> int | None:
    """Extract a 4-digit year from a string or int, return None if invalid."""
    if value is None:
        return None
    s = str(value)[:4]
    return int(s) if s.isdigit() else None
```

### Pseudocode for every resolved_* field

```python
# After merging all importer dicts into track_data:

mb = track_data          # fields from acoustid.py are flat in track_data
tags = track_data        # fields from tags.py are flat in track_data
es = track_data          # fields from essentia_analysis.py are flat in track_data

# resolved_title — never NULL: fall through to filename stem
resolved_title = next(
    (v for v in [track_data.get("title"), track_data.get("tag_title")] if v),
    Path(path).stem,     # filename stem, always present
)

# resolved_artist
resolved_artist = next(
    (v for v in [
        track_data.get("artist"),
        track_data.get("tag_artist"),
        track_data.get("discogs_artists_sort"),
    ] if v),
    None,
)

# resolved_bpm
tag_bpm_raw = track_data.get("tag_bpm")
tag_bpm = None
if tag_bpm_raw:
    try:
        tag_bpm = float(tag_bpm_raw)
    except (ValueError, TypeError):
        pass

resolved_bpm = next(
    (v for v in [track_data.get("bpm"), tag_bpm] if v),
    None,
)

# resolved_key
# Essentia key is stored as two separate fields: "key" (e.g. "C") and "key_scale" ("major"/"minor")
es_key = track_data.get("key")
es_key_scale = track_data.get("key_scale")
es_key_combined = f"{es_key} {es_key_scale}" if es_key and es_key_scale else None

resolved_key = next(
    (v for v in [
        es_key_combined,
        track_data.get("tag_key"),
        track_data.get("tag_initial_key_txxx"),
    ] if v),
    None,
)

# resolved_label
resolved_label = next(
    (v for v in [
        track_data.get("label"),          # mb_label from acoustid.py
        track_data.get("discogs_label"),
        track_data.get("tag_label"),
    ] if v),
    None,
)

# resolved_year
resolved_year = next(
    (v for v in [
        _year_from(track_data.get("year")),                         # mb_year (already int in acoustid.py)
        _year_from(track_data.get("discogs_year")),
        _year_from(track_data.get("discogs_master_year")),
        _year_from(track_data.get("tag_year_id3v24")),              # e.g. "2003-01-15" → "2003"
        _year_from(track_data.get("tag_year_id3v23")),              # e.g. "2003"
        _year_from(track_data.get("itunes_release_date")),          # e.g. "2005-01-01T00:00:00Z" → "2005"
    ] if v),
    None,
)

# resolved_artwork_url
resolved_artwork_url = next(
    (v for v in [
        track_data.get("itunes_artwork_url"),
        track_data.get("cover_art_url"),    # caa_url from cover_art.py
    ] if v),
    None,
)
```

### Key name mapping note

The acoustid importer returns keys without a `mb_` prefix in its dict:
- `"title"` (not `"mb_title"`)
- `"artist"` (not `"mb_artist"`)
- `"label"` (not `"mb_label"`)
- `"year"` (not `"mb_year"`)

These are mapped to `mb_*` columns in the database schema. The pipeline must rename them during the merge step:

```python
acoustid_result = fut_acoustid.result(...)
# Rename flat keys to db column names
mb_data = {
    "mb_recording_id":        acoustid_result.get("mb_recording_id"),
    "mb_release_id":          acoustid_result.get("mb_release_id"),
    "mb_artist_id":           acoustid_result.get("mb_artist_id"),
    "mb_release_group_id":    acoustid_result.get("mb_release_group_id"),
    "mb_release_group_type":  acoustid_result.get("mb_release_group_type"),
    "mb_title":               acoustid_result.get("title"),
    "mb_artist":              acoustid_result.get("artist"),
    "mb_artist_sort_name":    acoustid_result.get("artist_sort_name"),
    "mb_year":                acoustid_result.get("year"),
    "mb_duration_s":          acoustid_result.get("mb_duration_s"),
    "mb_isrc":                acoustid_result.get("isrc"),
    "mb_release_title":       acoustid_result.get("mb_release_title"),
    "mb_release_status":      acoustid_result.get("release_status"),
    "mb_release_country":     acoustid_result.get("release_country"),
    "mb_label":               acoustid_result.get("label"),
    "mb_catalogue_number":    acoustid_result.get("catalogue_number"),
    "mb_has_front_art":       acoustid_result.get("mb_has_front_art"),
    "mb_genres":              str(acoustid_result.get("genres") or []),
    "mb_tags":                str(acoustid_result.get("tags") or []),
    "mb_lookup_error":        acoustid_result.get("lookup_error"),
    "acoustid_id":            acoustid_result.get("acoustid_id"),
    "acoustid_score":         acoustid_result.get("acoustid_score"),
    "acoustid_match":         acoustid_result.get("acoustid_match"),
}
```

Similarly, the essentia importer returns keys without `es_` prefix (e.g. `"bpm"` not `"es_bpm"`). The merge step must rename these too.

Similarly, the cover_art importer returns `"cover_art_url"`, `"cover_art_source"`, `"cover_art_lookup_timestamp"` — these map to `caa_url`, `caa_source`, `caa_lookup_timestamp` in the database.

Tags importer returns flat keys like `"tag_title"`, `"file_path"`, `"file_format"`, `"duration_seconds"` — the column names differ slightly (e.g. `duration_seconds` → `tag_duration_seconds`).

**Conclusion:** the merge step is not a simple `dict.update()` — it requires an explicit column mapping layer. This should be a `_build_db_row(tag_result, acoustid_result, discogs_result, itunes_result, caa_result, essentia_result, resolved_fields, file_meta)` function that returns a fully-keyed dict matching the `tracks` schema exactly.

---

## Test Strategy

### Unit tests: mock importers, assert merge logic

The highest-value unit tests verify:
1. The column mapping layer (`_build_db_row`) — correct field names, correct fallback chain results.
2. The resolved field computation — correct priority ordering, None/empty-string handling.
3. The skip-check logic — correct hash and mtime comparison.

These tests should use `unittest.mock.patch` to replace individual importers with functions that return fixed dicts. No network calls, no filesystem reads beyond the test fixture.

```python
# pytest example
from unittest.mock import patch

def test_resolved_year_priority():
    with patch("backend.importer.pipeline.identify_track") as mock_acoustid:
        mock_acoustid.return_value = {"year": 2003, ...}
        result = import_track("/fake/path.mp3", ...)
    assert result["resolved_year"] == 2003
```

### Integration tests: real database, mocked importers, tmp_path

Use `pytest`'s built-in `tmp_path` fixture for a temporary SQLite database:

```python
def test_full_pipeline_writes_row(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    # ... run pipeline with mocked importers ...
    row = conn.execute("SELECT * FROM tracks WHERE file_path = ?", (path,)).fetchone()
    assert row["resolved_title"] is not None
```

This tests:
- The UPSERT SQL executes without error.
- The `id` is preserved on re-import (upsert, not replace).
- `crate_tracks` entries survive a re-import.
- The schema mapping is complete (no missing columns that would cause a SQL error).

### End-to-end tests: real importers, real file

For the concurrency and real-importer path, use a single known MP3 from the test fixtures directory with all API keys set. These tests are slow (network + CPU) and should be marked `@pytest.mark.slow` or run only in CI.

### Testing concurrency without wall-clock timing

To verify the concurrent execution order without relying on sleep/timing:

```python
import threading

call_order = []
lock = threading.Lock()

def mock_acoustid(*args):
    with lock:
        call_order.append("acoustid")
    return {}

def mock_itunes(*args):
    with lock:
        call_order.append("itunes")
    return {}

# After running pipeline:
assert "acoustid" in call_order
assert "itunes" in call_order
# discogs must be called AFTER acoustid (not concurrent with it)
assert call_order.index("discogs") > call_order.index("acoustid")
```

### Recommended test structure

```
backend/tests/test_importer/
    test_pipeline_merge.py      # unit: _build_db_row, resolved fields, column mapping
    test_pipeline_skip.py       # unit: hash check, mtime check
    test_pipeline_db.py         # integration: upsert, id preservation, foreign keys
    test_pipeline_e2e.py        # slow: real importers, real file, mark with @pytest.mark.slow
```

---

## Open Questions

1. **Essentia column name prefix:** `essentia_analysis.py` returns `"bpm"`, `"key"`, `"key_scale"` etc. (no `es_` prefix). The database schema has `es_bpm`, `es_key`, `es_key_scale`. The mapping must be documented and tested. Confirm the complete mapping before implementing `_build_db_row`.

2. **Tags column name discrepancies:** `tags.py` returns `"duration_seconds"` but the DB has `tag_duration_seconds`. `tags.py` returns `"file_format"` but the DB has `tag_file_format`. A full diff of tags return keys vs DB column names is needed.

3. **Discogs `discogs_styles_search` column:** The DB schema has `discogs_styles_search TEXT` but `discogs.py` does not return this key. Clarify whether this is a computed/normalised field or an oversight in the importer.

4. **Essentia `es_genre_top_labels_search` column:** Similarly, the DB has this column but `essentia_analysis.py` does not return it. Likely a normalised version for full-text search — needs specification.

5. **sqlite-vec DELETE+INSERT atomicity:** The DELETE then INSERT for `vec_tracks` must happen in the same transaction as the `tracks` UPSERT to prevent partial state. Confirm that `conn.execute()` in WAL mode with `conn.commit()` at the end of `import_track()` covers both writes atomically.

6. **WSL2 + Essentia interaction with ThreadPoolExecutor:** The CLAUDE.md note says Essentia is "not fully thread-safe — algorithm instances must not be shared across threads." In the pipeline, each call to `analyse_track()` creates fresh algorithm instances inside the function (confirmed by reading `essentia_analysis.py`). This is safe as long as `analyse_track()` is called with `max_workers=1` for the Essentia slot (the other two workers handle acoustid and iTunes). Verify this is the case — or add a note to always instantiate a fresh `EssentiaConfig` per call.

7. **`mb_genres` and `mb_tags` serialisation:** `acoustid.py` returns `genres` as `[]` (always empty — musicbrainzngs 0.7.1 does not support the genres include) and `tags` as a list of strings. These are stored as `mb_genres TEXT` and `mb_tags TEXT` in the DB. The pipeline must serialise these lists to strings. Confirm the format: JSON `json.dumps(list)` is preferable to `str(list)` for round-tripping.

8. **`file_hash` algorithm stability:** If the algorithm is ever changed from MD5 to SHA-1, all stored hashes become invalid and every track would be re-imported. Consider storing the algorithm name alongside the hash (`"md5:abc123..."`) to allow future migrations.
