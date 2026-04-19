# Implementation Plan: Import Pipeline Orchestrator

_Written 2026-04-19. All decisions grounded in `md/research/research-pipeline.md` and the eight source files listed in the task prompt._

---

## Overview

`pipeline.py` is the glue layer for the Crate import system. It receives a single audio file path and a database connection, calls all six importers in the order mandated by their data dependencies, merges their flat dicts through an explicit column-mapping layer, computes seven `resolved_*` canonical fields via fallback chains, and writes a single row to the `tracks` table. It also optionally generates a sentence-transformers embedding and writes it to `vec_tracks`. The pipeline never raises to the caller — it logs failures and writes whatever partial data it has. It does not parse tags, score candidates, or make curation decisions; those belong in the importers or later stages.

---

## Module Interface

### `import_track`

```python
def import_track(
    file_path: str | Path,
    db: sqlite3.Connection,
    config: PipelineConfig,
    progress_callback: Callable[[str], None] | None = None,
) -> dict | None:
```

- **`file_path`**: absolute path to the audio file.
- **`db`**: an open `sqlite3.Connection` returned by `get_db()`. The caller owns the connection lifetime.
- **`config`**: a single `PipelineConfig` wrapping all per-importer configs (see Config Design section).
- **`progress_callback`**: optional; called with a human-readable status string at key steps (hash hit, importer finish, write complete). Kept simple — `Callable[[str], None]` is sufficient for a single-track function. Batch progress is handled by `import_tracks()`.
- **Return value**: the fully-merged + resolved `dict` that was written to the DB (including all column keys), or `None` on a hash-hit skip. On partial failure (some importers returned empty dicts), the return value will have `None` for the affected fields.
- **Error contract**: the function never raises. Any exception at any step is caught, logged at ERROR, and the function returns `None`.

### `import_tracks`

```python
def import_tracks(
    paths: list[str | Path],
    db: sqlite3.Connection,
    config: PipelineConfig,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> None:
```

- Discovers no files itself — it receives a pre-built list from the caller (see batch entry point section).
- `on_progress(done: int, total: int, current_path: str)` is called after each track completes. It runs in the main thread, so it is safe to update `tqdm` from it.
- `tqdm` integration belongs in the calling script (`scripts/import_library.py`), not here.

### Batch entry point

`import_tracks()` lives in `pipeline.py`. File discovery (walking the folder, filtering by extension) belongs in a separate calling script or `scripts/import_library.py` — it is not pipeline logic. The pipeline only accepts a list of paths.

---

## Change Detection

### Hash algorithm

Use **MD5**. This is a change-detection mechanism, not a security mechanism. MD5 is the fastest hashlib algorithm and is sufficient for detecting file content changes. A 300 MB FLAC hashes in ~0.5s vs ~1.5s for SHA-256.

### Chunked hashing — exact pattern

```python
import hashlib

def _hash_file(path: str, chunk_size: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

64 KB chunks minimise Python loop overhead without memory pressure. Walrus operator requires Python 3.8+; codebase targets 3.11+.

### mtime storage

Store as **TEXT** containing the float string representation: `str(os.stat(path).st_mtime)`. The DB column `file_modified_at TEXT` already uses this type. String avoids SQLite float affinity truncation and round-trips exactly.

### Skip logic — exact SQL and Python

**Strategy**: check mtime first (cheap, O(1)). If mtime is unchanged, skip without hashing — for a batch of 10,000 unchanged tracks this avoids 10,000 file reads. If mtime changed (or no stored record), hash and proceed.

```python
import os

def _check_skip(path: str, db: sqlite3.Connection) -> bool:
    """Return True if the file is already imported and unchanged."""
    current_mtime = str(os.stat(path).st_mtime)
    row = db.execute(
        "SELECT file_modified_at, file_hash FROM tracks WHERE file_path = ?",
        (path,)
    ).fetchone()
    if row is None:
        return False  # new file — never imported
    if row["file_modified_at"] == current_mtime:
        return True   # mtime unchanged — skip (fast path)
    # mtime changed — verify hash before re-importing
    current_hash = _hash_file(path)
    if current_hash == row["file_hash"]:
        return True   # content unchanged (touch/copy artifact) — skip
    return False      # content changed — re-import
```

**On a hash hit:** return `None` immediately. Log at DEBUG. Do not call any importer.

---

## Execution Order and Concurrency

### Dependency diagram

```
Step 1   _check_skip()              — synchronous; return None on hit
Step 2   _hash_file() + os.stat()   — synchronous; compute hash + mtime for INSERT
Step 3   read_tags(path)            — synchronous, instant; provides inputs for Discogs + iTunes
Step 4   ThreadPoolExecutor(max_workers=3):
           fut_acoustid = submit(identify_track, path, config.acoustid)
           fut_itunes   = submit(fetch_itunes, artist, title, duration, config.itunes)
           fut_essentia = submit(analyse_track, path, config.essentia)  # only if _ESSENTIA_AVAILABLE
         acoustid_result  = fut_acoustid.result(timeout=90)
         itunes_result    = fut_itunes.result(timeout=30)
         essentia_result  = fut_essentia.result(timeout=300) if fut_essentia else {}
Step 5   fetch_discogs_metadata(...)   — synchronous; inputs from steps 3 + 4a
Step 6   fetch_cover_art(...)          — synchronous; inputs from step 4a
Step 7   _build_db_row(...)            — merge + column mapping + resolved_* computation
Step 8   INSERT INTO tracks ... ON CONFLICT(file_path) DO UPDATE SET ...
Step 9   (if vec available) generate embedding → DELETE + INSERT INTO vec_tracks
```

Steps 5 and 6 are **sequential** after the executor exits, not concurrent with each other. Both depend on step 4a (acoustid), so neither can start before that future resolves. Running them concurrently would require a second executor or nested submit, adding complexity for negligible gain (Discogs is the slow one; CAA is fast). Sequential is simpler and correct.

### Exact ThreadPoolExecutor pattern

```python
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

with ThreadPoolExecutor(max_workers=3) as executor:
    fut_acoustid = executor.submit(identify_track, str(path), config.acoustid)
    fut_itunes   = executor.submit(
        fetch_itunes,
        tag_artist or "",
        tag_title or "",
        tags.get("duration_seconds"),
        config.itunes,
    )
    if _ESSENTIA_AVAILABLE:
        fut_essentia = executor.submit(analyse_track, str(path), config.essentia)
    else:
        fut_essentia = None
# Executor has shut down (wait=True) — all threads complete before this line.

def _collect(future, name: str, timeout: int) -> dict:
    if future is None:
        return {}
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        tlog.warning("%s timed out after %ds", name, timeout)
        return {}
    except Exception as exc:
        tlog.error("%s raised unexpectedly: %s", name, exc)
        return {}

acoustid_result  = _collect(fut_acoustid, "acoustid",  timeout=90)
itunes_result    = _collect(fut_itunes,   "itunes",     timeout=30)
essentia_result  = _collect(fut_essentia, "essentia",   timeout=300)
```

**Timeout rationale** (from research doc):
- AcoustID + MusicBrainz: up to 3 sequential network calls with 1s delays = 90s generous.
- iTunes: single call with 3s rate-limit delay + country fallbacks = 30s sufficient.
- Essentia: CPU-bound, 5–30s standard + ML models on long tracks = 300s.

**On timeout**: the field dict defaults to `{}`. Steps 5 and 6 still run with degraded inputs:
- Discogs with empty acoustid → artist/title from tags only (label+title and artist+title strategies still possible; label and catno inputs from acoustid/MB fall back to tags values).
- Cover Art → `release_mbid=None, release_group_mbid=None` → returns `_no_art_dict()` immediately.

### Inputs for step 5 (Discogs) from acoustid result

The acoustid result uses non-prefixed keys. Extract:

```python
mb_artist    = acoustid_result.get("artist")
mb_title     = acoustid_result.get("title")
mb_label     = acoustid_result.get("label")
mb_catno     = acoustid_result.get("catalogue_number")
mb_barcode   = None   # acoustid/MB does not return barcode; Discogs skips to label+title
mb_year      = acoustid_result.get("year")
```

Discogs inputs use tag fields as the primary source and supplement with MB where tags are absent:

```python
discogs_result = fetch_discogs_metadata(
    artist  = tags.get("tag_artist") or mb_artist,
    title   = tags.get("tag_title")  or mb_title,
    label   = tags.get("tag_label")  or mb_label,
    catno   = tags.get("tag_catalogue_no") or mb_catno,
    barcode = None,
    year    = mb_year or _year_from(tags.get("tag_year_id3v24")),
    client  = config.discogs_client,
    config  = config.discogs,
)
```

### Inputs for step 6 (Cover Art) from acoustid result

```python
caa_result = fetch_cover_art(
    release_mbid       = acoustid_result.get("mb_release_id"),
    release_group_mbid = acoustid_result.get("mb_release_group_id"),
    config             = config.cover_art,
    mb_has_front_art   = acoustid_result.get("mb_has_front_art"),
)
```

### Discogs client thread safety

The `discogs_client.Client` instance is **created in `PipelineConfig.__post_init__`** (once per pipeline session) and reused across tracks. The python3-discogs-client library is thread-safe for concurrent reads (HTTP GET only) — each call creates its own `requests.Session` internally. However, since Discogs runs in step 5 (synchronous, not in the executor), thread safety is not a concern for this pipeline's usage pattern.

---

## Essentia Availability

### Detection method — exact pattern

```python
def _is_wsl2() -> bool:
    """Return True if running inside WSL2."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False
```

On native Windows, `/proc` does not exist → `OSError` → returns `False`. On WSL2, `/proc/version` contains `"microsoft"`. On native Linux, the string is absent → `False` (correct — Essentia's WSL2 constraint is about Windows+WSL2 as the dev environment, but native Linux would also work; treat native Linux as Essentia-capable by checking for successful import instead if needed).

**Refined detection**: combine `/proc/version` check with `try: import essentia` to handle native Linux correctly:

```python
def _is_essentia_available() -> bool:
    try:
        import essentia.standard  # noqa: F401
        return True
    except ImportError:
        return False
```

Use import-based detection as the primary check. This is more robust: if Essentia is installed and importable (WSL2, native Linux, or future Windows binaries), use it; otherwise skip.

### Module-level cache

```python
# At module top level — evaluated once at import time
_ESSENTIA_AVAILABLE: bool = _is_essentia_available()
```

### Logging

```python
# Immediately after the module-level assignment — logged once per process start
if not _ESSENTIA_AVAILABLE:
    logger.info(
        "Essentia audio analysis disabled: essentia package not importable. "
        "Re-run from WSL2 with `uv sync --extra analysis` to enable."
    )
```

Log at INFO, not WARNING — this is expected behaviour on the Windows dev environment. No per-track log is needed; inside `import_track()` simply pass `fut_essentia = None`.

---

## Merge Strategy

### Approach: explicit `_build_db_row()` function

Because every importer returns keys that differ from the database column names, a simple `dict.update()` chain is insufficient. The merge step is an explicit column-mapping function:

```python
def _build_db_row(
    file_meta: dict,        # {file_path, file_hash, file_modified_at, file_size_bytes}
    tags: dict,
    acoustid: dict,
    discogs: dict,
    itunes: dict,
    caa: dict,
    essentia: dict,
    resolved: dict,
) -> dict:
```

This function builds a dict keyed exactly to the `tracks` schema columns by pulling from each importer's returned keys.

### Complete key mapping table

#### File metadata (not from any importer — added by pipeline)

| DB column | Source |
|---|---|
| `file_path` | `os.fspath(path)` |
| `file_hash` | `_hash_file(path)` |
| `file_size_bytes` | `os.stat(path).st_size` |
| `file_modified_at` | `str(os.stat(path).st_mtime)` |
| `imported_at` | `datetime.now(UTC).isoformat()` |

#### Tags (tags.py return key → DB column)

| tags.py key | DB column |
|---|---|
| `file_format` | `tag_file_format` |
| `duration_seconds` | `tag_duration_seconds` |
| `bitrate_bps` | `tag_bitrate_bps` |
| `bitrate_mode` | `tag_bitrate_mode` |
| `sample_rate_hz` | `tag_sample_rate_hz` |
| `channels` | `tag_channels` |
| `bits_per_sample` | `tag_bits_per_sample` |
| `encoder_info` | `tag_encoder_info` |
| `is_sketchy` | `tag_is_sketchy` |
| `tag_title` | `tag_title` _(same)_ |
| `tag_artist` | `tag_artist` _(same)_ |
| `tag_album_artist` | `tag_album_artist` _(same)_ |
| `tag_album` | `tag_album` _(same)_ |
| `tag_label` | `tag_label` _(same)_ |
| `tag_catalogue_no` | `tag_catalogue_no` _(same)_ |
| `tag_genre` | `tag_genre` _(same)_ |
| `tag_comment` | `tag_comment` _(same)_ |
| `tag_isrc` | `tag_isrc` _(same)_ |
| `tag_copyright` | `tag_copyright` _(same)_ |
| `tag_year_id3v24` | `tag_year_id3v24` _(same)_ |
| `tag_year_id3v23` | `tag_year_id3v23` _(same)_ |
| `tag_date_released` | `tag_date_released` _(same)_ |
| `tag_date_original` | `tag_date_original` _(same)_ |
| `tag_date_vorbis` | `tag_date_vorbis` _(same)_ |
| `tag_date_mp4` | `tag_date_mp4` _(same)_ |
| `tag_track_number` | `tag_track_number` _(same)_ |
| `tag_disc_number` | `tag_disc_number` _(same)_ |
| `tag_bpm` | `tag_bpm` _(same)_ |
| `tag_key` | `tag_key` _(same)_ |
| `tag_energy` | `tag_energy` _(same)_ |
| `tag_initial_key_txxx` | `tag_initial_key_txxx` _(same)_ |
| `has_embedded_art` | `tag_has_embedded_art` |
| `has_serato_tags` | `tag_has_serato_tags` |
| `has_traktor_tags` | `tag_has_traktor_tags` |
| `has_rekordbox_tags` | `tag_has_rekordbox_tags` |
| `tag_id3_version` | `tag_id3_version` _(same)_ |
| `tag_format_type` | `tag_format_type` _(same)_ |
| `tags_present` | `tag_tags_present` |
| `tags_error` | `tag_error` |

#### AcoustID / MusicBrainz (acoustid.py return key → DB column)

| acoustid.py key | DB column |
|---|---|
| `acoustid_id` | `acoustid_id` _(same)_ |
| `acoustid_score` | `acoustid_score` _(same)_ |
| `acoustid_match` | `acoustid_match` _(same)_ |
| `mb_recording_id` | `mb_recording_id` _(same)_ |
| `mb_release_id` | `mb_release_id` _(same)_ |
| `mb_artist_id` | `mb_artist_id` _(same)_ |
| `mb_release_group_id` | `mb_release_group_id` _(same)_ |
| `mb_release_group_type` | `mb_release_group_type` _(same)_ |
| `title` | `mb_title` |
| `artist` | `mb_artist` |
| `artist_sort_name` | `mb_artist_sort_name` |
| `year` | `mb_year` |
| `mb_duration_s` | `mb_duration_s` _(same)_ |
| `isrc` | `mb_isrc` |
| `mb_release_title` | `mb_release_title` _(same)_ |
| `release_status` | `mb_release_status` |
| `release_country` | `mb_release_country` |
| `label` | `mb_label` |
| `catalogue_number` | `mb_catalogue_number` |
| `mb_has_front_art` | `mb_has_front_art` _(same)_ |
| `genres` | `mb_genres` (JSON serialise: `json.dumps(v or [])`) |
| `tags` | `mb_tags` (JSON serialise: `json.dumps(v or [])`) |
| `lookup_error` | `mb_lookup_error` |

#### Discogs (discogs.py return keys are already prefixed `discogs_*` — direct mapping, all keys same)

All keys returned by `discogs.py` match their DB column names exactly. Pass them through directly. The DB has one additional column not returned by the importer:

| DB column | Source |
|---|---|
| `discogs_styles_search` | Computed by pipeline: `" ".join(json.loads(discogs.get("discogs_styles") or "[]"))` — a space-joined plain-text version of the styles list for FTS. Set `None` if `discogs_styles` is null. |
| `discogs_error` | Direct from discogs dict (already present if set) |

#### iTunes (itunes.py return keys are already prefixed `itunes_*` — direct mapping, all keys same)

#### Cover Art Archive (cover_art.py return key → DB column)

| cover_art.py key | DB column |
|---|---|
| `cover_art_url` | `caa_url` |
| `cover_art_source` | `caa_source` |
| `cover_art_lookup_timestamp` | `caa_lookup_timestamp` |
| `cover_art_error` | `caa_error` (may be absent; default `None`) |

#### Essentia (essentia_analysis.py return key → DB column)

| essentia_analysis.py key | DB column |
|---|---|
| `bpm` | `es_bpm` |
| `bpm_confidence` | `es_bpm_confidence` |
| `beat_ticks` | `es_beat_ticks` (JSON serialise list) |
| `bpm_estimates` | `es_bpm_estimates` (JSON serialise list) |
| `bpm_intervals` | `es_bpm_intervals` (JSON serialise list) |
| `key` | `es_key` |
| `key_scale` | `es_key_scale` |
| `key_strength` | `es_key_strength` |
| `tuning_frequency_hz` | `es_tuning_frequency_hz` |
| `tuning_cents` | `es_tuning_cents` |
| `integrated_loudness` | `es_integrated_loudness` |
| `loudness_range` | `es_loudness_range` |
| `dynamic_complexity` | `es_dynamic_complexity` |
| `dynamic_complexity_loudness` | `es_dynamic_complexity_loudness` |
| `spectral_centroid_hz` | `es_spectral_centroid_hz` |
| `sub_bass_ratio` | `es_sub_bass_ratio` |
| `high_freq_ratio` | `es_high_freq_ratio` |
| `mfcc_mean` | `es_mfcc_mean` (JSON serialise list) |
| `mfcc_var` | `es_mfcc_var` (JSON serialise list) |
| `bark_bands_mean` | `es_bark_bands_mean` (JSON serialise list) |
| `danceability` | `es_danceability` |
| `danceability_dfa` | `es_danceability_dfa` (JSON serialise list) |
| `onset_times` | `es_onset_times` (JSON serialise list) |
| `onset_rate` | `es_onset_rate` |
| `pitch_frames` | `es_pitch_frames` (JSON serialise list) |
| `pitch_confidence_frames` | `es_pitch_confidence_frames` (JSON serialise list) |
| `genre_probabilities` | `es_genre_probabilities` (JSON serialise list) |
| `genre_top_labels` | `es_genre_top_labels` (JSON serialise list) |
| — | `es_genre_top_labels_search` (computed: `" ".join(genre_top_labels or [])`) |
| `arousal` | `es_arousal` |
| `valence` | `es_valence` |
| `mood_aggressive` | `es_mood_aggressive` |
| `mood_happy` | `es_mood_happy` |
| `mood_party` | `es_mood_party` |
| `mood_relaxed` | `es_mood_relaxed` |
| `mood_sad` | `es_mood_sad` |
| `instrument_probabilities` | `es_instrument_probabilities` (JSON serialise list) |
| `instrument_top_labels` | `es_instrument_top_labels` (JSON serialise list) |
| `moodtheme_probabilities` | `es_moodtheme_probabilities` (JSON serialise list) |
| `moodtheme_top_labels` | `es_moodtheme_top_labels` (JSON serialise list) |
| `ml_danceability` | `es_ml_danceability` |
| `voice_probability` | `es_voice_probability` |
| `voice_probability_musicnn` | `es_voice_probability_musicnn` |
| `essentia_version` | `es_version` |
| `analysis_timestamp` | `es_analysis_timestamp` |
| `analysis_error` | `es_analysis_error` |

The `embedding` key from essentia is **not** written to the `tracks` table — it goes to `vec_tracks` separately (see SQLite Write section). `embedding_track`, `embedding_artist`, `embedding_label`, `embedding_release` are not currently in the DB schema; omit them or store as TEXT if schema is extended.

### Merge conflict policy

Key namespacing (`tag_*`, `acoustid_*`, `mb_*`, `discogs_*`, `itunes_*`, `caa_*`, `es_*`) means there are **no key conflicts between importer dicts**. The conflict policy is stated for completeness: the last writer wins in a naive `dict.update()`, but `_build_db_row()` explicitly maps each source key to its DB column name — there are no two sources writing the same column.

### Empty dict handling

An importer that fails returns `{}` or its null dict (all keys set to `None`). Both are safe: `_build_db_row()` uses `.get()` with a `None` default for every source key. Missing importer output → all corresponding DB columns are `None`. The INSERT still executes.

### Validation

Do **not** validate the merged dict against the schema at runtime. Trust `_build_db_row()` to produce the correct shape. If a column is missing, SQLite will raise `OperationalError` on INSERT — this is caught by the error handler and logged at ERROR. Schema-level test coverage (integration test with a real DB) catches this at development time.

---

## Resolved Field Computation

All resolved fields are computed inside `_build_db_row()` after all importer dicts are available. The `next(..., default)` pattern skips both `None` and `""` (both are falsy).

### Helper

```python
def _year_from(value) -> int | None:
    """Extract a 4-digit year integer from a string, int, or None. Returns None if invalid."""
    if value is None:
        return None
    s = str(value)[:4]
    return int(s) if s.isdigit() else None
```

### Python expressions for every resolved field

```python
# resolved_title — never NULL; falls back to filename stem
resolved_title = next(
    (v for v in [acoustid.get("title"), tags.get("tag_title")] if v),
    Path(file_path).stem,
)

# resolved_artist — may be NULL
resolved_artist = next(
    (v for v in [
        acoustid.get("artist"),
        tags.get("tag_artist"),
        discogs.get("discogs_artists_sort"),
    ] if v),
    None,
)

# resolved_bpm — REAL; tag_bpm is a string (e.g. "128.0"), cast safely
_tag_bpm_raw = tags.get("tag_bpm")
_tag_bpm = None
if _tag_bpm_raw:
    try:
        _tag_bpm = float(_tag_bpm_raw)
    except (ValueError, TypeError):
        pass

resolved_bpm = next(
    (v for v in [essentia.get("bpm"), _tag_bpm] if v),
    None,
)

# resolved_key — Essentia returns two fields; combine them
_es_key       = essentia.get("key")
_es_key_scale = essentia.get("key_scale")
_es_key_combined = f"{_es_key} {_es_key_scale}" if _es_key and _es_key_scale else None

resolved_key = next(
    (v for v in [
        _es_key_combined,
        tags.get("tag_key"),
        tags.get("tag_initial_key_txxx"),
    ] if v),
    None,
)

# resolved_label
resolved_label = next(
    (v for v in [
        acoustid.get("label"),          # mb_label in the importer's flat dict
        discogs.get("discogs_label"),
        tags.get("tag_label"),
    ] if v),
    None,
)

# resolved_year — INTEGER; all sources are strings or ints; use _year_from() on all
resolved_year = next(
    (v for v in [
        _year_from(acoustid.get("year")),               # already int from MB, but safe to pass
        _year_from(discogs.get("discogs_year")),
        _year_from(discogs.get("discogs_master_year")),
        _year_from(tags.get("tag_year_id3v24")),        # e.g. "2003-01-15" → 2003
        _year_from(tags.get("tag_year_id3v23")),        # e.g. "2003"
        _year_from(itunes.get("itunes_release_date")),  # e.g. "2005-01-01T00:00:00Z" → 2005
    ] if v),
    None,
)

# resolved_artwork_url
resolved_artwork_url = next(
    (v for v in [
        itunes.get("itunes_artwork_url"),
        caa.get("cover_art_url"),
    ] if v),
    None,
)
```

**None vs "" handling**: `next((v for v in [...] if v), None)` treats both `None` and `""` as absent. An empty string tag is not a valid value. This is correct.

---

## SQLite Write

### INSERT pattern — UPSERT, not INSERT OR REPLACE

**Decision: use `INSERT INTO ... ON CONFLICT(file_path) DO UPDATE SET ...`** (UPSERT syntax, SQLite ≥ 3.24.0).

`INSERT OR REPLACE` is implemented as DELETE + INSERT. It assigns a **new AUTOINCREMENT id**, which cascades deletes to `crate_tracks` and `crate_corrections` via `ON DELETE CASCADE` — destroying crate membership on every re-import. UPSERT performs an in-place UPDATE, preserving the original `id` and all foreign key relationships. This is confirmed by the research doc and `sqlite.org` documentation.

### Exact SQL pattern

Write the INSERT statement dynamically from the column list to avoid manually maintaining a 180-column SQL string. Build once at module import time:

```python
import json
from datetime import UTC, datetime

# All tracks table columns in schema order (exclude 'id' — it is AUTOINCREMENT)
_TRACKS_COLUMNS = [
    "file_path", "file_hash", "file_size_bytes", "file_modified_at",
    "tag_file_format", "tag_duration_seconds", "tag_bitrate_bps", "tag_bitrate_mode",
    "tag_sample_rate_hz", "tag_channels", "tag_bits_per_sample", "tag_encoder_info",
    "tag_is_sketchy",
    "tag_title", "tag_artist", "tag_album_artist", "tag_album", "tag_label",
    "tag_catalogue_no", "tag_genre", "tag_comment", "tag_isrc", "tag_copyright",
    "tag_year_id3v24", "tag_year_id3v23", "tag_date_released", "tag_date_original",
    "tag_date_vorbis", "tag_date_mp4", "tag_track_number", "tag_disc_number",
    "tag_bpm", "tag_key", "tag_energy", "tag_initial_key_txxx",
    "tag_has_embedded_art", "tag_has_serato_tags", "tag_has_traktor_tags",
    "tag_has_rekordbox_tags", "tag_id3_version", "tag_format_type",
    "tag_tags_present", "tag_error",
    "acoustid_id", "acoustid_score", "acoustid_match",
    "mb_recording_id", "mb_release_id", "mb_artist_id", "mb_release_group_id",
    "mb_release_group_type", "mb_title", "mb_artist", "mb_artist_sort_name",
    "mb_year", "mb_duration_s", "mb_isrc", "mb_release_title", "mb_release_status",
    "mb_release_country", "mb_label", "mb_catalogue_number", "mb_has_front_art",
    "mb_genres", "mb_tags", "mb_lookup_error",
    "discogs_release_id", "discogs_master_id", "discogs_confidence",
    "discogs_search_strategy", "discogs_url", "discogs_title", "discogs_year",
    "discogs_country", "discogs_released", "discogs_released_formatted",
    "discogs_status", "discogs_data_quality", "discogs_notes", "discogs_artists_sort",
    "discogs_num_for_sale", "discogs_lowest_price", "discogs_label_id", "discogs_label",
    "discogs_catno", "discogs_label_entity_type", "discogs_artists", "discogs_genres",
    "discogs_styles", "discogs_styles_search", "discogs_format_names",
    "discogs_format_descs", "discogs_producers", "discogs_remixers",
    "discogs_extraartists_raw", "discogs_labels_raw", "discogs_tracklist",
    "discogs_barcodes", "discogs_matrix_numbers", "discogs_have", "discogs_want",
    "discogs_rating_avg", "discogs_rating_count", "discogs_master_year",
    "discogs_master_most_recent_id", "discogs_master_url", "discogs_lookup_timestamp",
    "discogs_error",
    "itunes_track_id", "itunes_artist_id", "itunes_collection_id", "itunes_confidence",
    "itunes_track_name", "itunes_artist_name", "itunes_collection_name",
    "itunes_release_date", "itunes_track_time_ms", "itunes_disc_count",
    "itunes_disc_number", "itunes_track_count", "itunes_track_number", "itunes_genre",
    "itunes_track_explicit", "itunes_is_streamable", "itunes_artwork_url",
    "itunes_track_url", "itunes_artist_url", "itunes_collection_url",
    "itunes_collection_artist_id", "itunes_collection_artist_name",
    "itunes_search_strategy", "itunes_country", "itunes_lookup_timestamp",
    "itunes_error",
    "caa_url", "caa_source", "caa_lookup_timestamp", "caa_error",
    "es_bpm", "es_bpm_confidence", "es_beat_ticks", "es_bpm_estimates",
    "es_bpm_intervals", "es_key", "es_key_scale", "es_key_strength",
    "es_tuning_frequency_hz", "es_tuning_cents", "es_integrated_loudness",
    "es_loudness_range", "es_dynamic_complexity", "es_dynamic_complexity_loudness",
    "es_spectral_centroid_hz", "es_sub_bass_ratio", "es_high_freq_ratio",
    "es_mfcc_mean", "es_mfcc_var", "es_bark_bands_mean", "es_danceability",
    "es_danceability_dfa", "es_onset_times", "es_onset_rate", "es_pitch_frames",
    "es_pitch_confidence_frames", "es_genre_probabilities", "es_genre_top_labels",
    "es_genre_top_labels_search", "es_arousal", "es_valence", "es_mood_aggressive",
    "es_mood_happy", "es_mood_party", "es_mood_relaxed", "es_mood_sad",
    "es_instrument_probabilities", "es_instrument_top_labels",
    "es_moodtheme_probabilities", "es_moodtheme_top_labels", "es_ml_danceability",
    "es_voice_probability", "es_voice_probability_musicnn", "es_version",
    "es_analysis_timestamp", "es_analysis_error",
    "resolved_title", "resolved_artist", "resolved_bpm", "resolved_key",
    "resolved_label", "resolved_year", "resolved_artwork_url",
    "last_played_at", "play_count",
    "imported_at", "tags_imported_at", "acoustid_imported_at", "discogs_imported_at",
    "itunes_imported_at", "caa_imported_at", "essentia_imported_at",
]

_cols_str    = ", ".join(_TRACKS_COLUMNS)
_vals_str    = ", ".join(f":{c}" for c in _TRACKS_COLUMNS)
# Update all columns except file_path (the conflict target) and id (never touched)
_update_str  = ", ".join(
    f"{c} = excluded.{c}" for c in _TRACKS_COLUMNS if c != "file_path"
)

_INSERT_SQL = f"""
INSERT INTO tracks ({_cols_str})
VALUES ({_vals_str})
ON CONFLICT(file_path) DO UPDATE SET
    {_update_str}
"""
```

### Execution

```python
try:
    db.execute(_INSERT_SQL, row)
    db.commit()
    tlog.info("Wrote track: %s", row.get("resolved_title"))
except Exception as exc:
    tlog.error("SQLite write failed: %s", exc)
    return None
```

### Parameter dict construction

`_build_db_row()` returns a dict keyed exactly to `_TRACKS_COLUMNS`. Every column has an entry (missing values are `None`). Named parameters (`:key`) are used — they are immune to column order and are more readable than positional `?` for a 180-column INSERT.

### Per-importer timestamps

The pipeline sets the `*_imported_at` timestamp columns to `datetime.now(UTC).isoformat()` for each importer that returned data, `None` otherwise. These are set inside `_build_db_row()`.

### Embeddings write — separate from tracks INSERT

Embeddings are written **after** the tracks UPSERT commits. The `track_id` is retrieved with a SELECT (not `lastrowid`, which is unreliable with UPSERT):

```python
cursor = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(path),))
track_id = cursor.fetchone()["id"]

# DELETE then INSERT (vec0 does not support UPSERT)
db.execute("DELETE FROM vec_tracks WHERE track_id = ?", (track_id,))
db.execute(
    "INSERT INTO vec_tracks(track_id, embedding) VALUES (?, ?)",
    (track_id, vec_bytes),
)
db.commit()
```

The embedding is generated inside `import_track()` after `_build_db_row()`, using sentence-transformers on the resolved fields. Both the tracks write and the vec_tracks write are wrapped in the same error handler; if the vec write fails, log at WARNING and continue (the track row is already written and committed).

The embedding text is constructed from resolved fields:
```python
embed_text = " ".join(filter(None, [
    row.get("resolved_artist"),
    row.get("resolved_title"),
    row.get("resolved_label"),
    str(row["resolved_year"]) if row.get("resolved_year") else None,
]))
```

---

## Error Handling and Logging

### Logger setup

```python
import logging

logger = logging.getLogger(__name__)  # "backend.importer.pipeline"
```

One logger per module, named by `__name__`. No handlers or formatters set here — the application root handler controls output format.

### LoggerAdapter for per-track context

```python
class _TrackLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra['path']}] {msg}", kwargs
```

Created inside `import_track()`:
```python
tlog = _TrackLogger(logger, {"path": os.fspath(path)})
```

All log calls inside `import_track()` use `tlog` — every log line includes the file path. The module-level `logger` is used only for the one-time Essentia availability message.

### Log levels per event

| Event | Level | Message |
|---|---|---|
| Hash hit (mtime match, skip) | DEBUG | `"Skipping unchanged file"` |
| Hash hit (hash verified, skip) | DEBUG | `"Hash confirmed unchanged, skipping"` |
| Importer timeout | WARNING | `"{name} timed out after {N}s"` |
| Importer returned error flag | WARNING | `"{name} returned error: {error_value}"` |
| Successful DB write | INFO | `"Wrote track: {resolved_title}"` |
| SQLite write failure | ERROR | `"SQLite write failed: {exc}"` |
| Unexpected exception in import_track | ERROR | `"Unexpected error: {exc}"` (with `exc_info=True`) |
| Essentia unavailable (once) | INFO | `"Essentia disabled: ..."` |

### `read_tags()` failure handling

`read_tags()` never raises — it returns a dict with `tags_error` set and all tag fields as `None`. If `tags_error` is set:
- Log at WARNING: `tlog.warning("read_tags error: %s", tags.get("tags_error"))`
- Continue. The pipeline uses empty-string/None fallbacks in the resolved field chains.
- `resolved_title` falls back to `Path(path).stem` — guaranteed non-null.
- `resolved_artist` and others will be `None` — acceptable, written to DB.

The pipeline still runs all importers even when tags fail, because iTunes and Discogs can use filename-parsed artist/title (handled at the calling level — if both `tag_artist` and MB `artist` are None, Discogs and iTunes will receive empty strings and will likely return `_no_match_dict()`).

### Batch-level resilience

`import_tracks()` wraps each `import_track()` call in a `try/except`:

```python
for i, path in enumerate(paths):
    try:
        import_track(path, db, config)
    except Exception as exc:
        # import_track should never raise, but guard defensively
        logger.error("Unhandled exception for %s: %s", path, exc, exc_info=True)
    if on_progress:
        on_progress(i + 1, len(paths), str(path))
```

---

## Progress Reporting

### Callback signature

```python
on_progress: Callable[[int, int, str], None] | None = None
# on_progress(done: int, total: int, current_path: str)
```

`done` is 1-indexed (count of completed tracks), `total` is the list length, `current_path` is the path that just finished. Called after each track completes (whether it was a skip, a write, or an error). Simple enough for any consumer to implement.

### `progress_callback` in `import_track`

The single-track function accepts a simpler `Callable[[str], None]` callback for status strings (`"hashing"`, `"reading tags"`, `"running importers"`, `"writing"`, `"skipped"`, `"done"`). This is optional and may be omitted in the initial implementation.

### tqdm integration — calling script only

```python
# scripts/import_library.py — NOT in pipeline.py
from tqdm import tqdm
from backend.importer.pipeline import import_tracks, PipelineConfig
from backend.database import get_db

paths = [...]  # discovered by the caller
db = get_db()
config = PipelineConfig()

with tqdm(total=len(paths), unit="track") as pbar:
    def on_progress(done, total, path):
        pbar.set_postfix_str(Path(path).name[:40])
        pbar.update(1)

    import_tracks(paths, db, config, on_progress=on_progress)
```

---

## Config Design

### Decision: single `PipelineConfig` wrapping per-importer configs

Keeps the `import_track()` signature to one config argument. Per-importer configs remain separate dataclasses in `config.py` (already defined). `PipelineConfig` is added to `config.py` alongside them.

### `PipelineConfig` — full field table

| Field | Type | Default | Source |
|---|---|---|---|
| `acoustid` | `AcoustIDConfig` | `field(default_factory=AcoustIDConfig)` | reads `ACOUSTID_API_KEY`, `MUSICBRAINZ_APP` from env |
| `discogs` | `DiscogsConfig` | `field(default_factory=DiscogsConfig)` | reads `DISCOGS_TOKEN`, `DISCOGS_APP` from env |
| `itunes` | `ItunesConfig` | `field(default_factory=ItunesConfig)` | no env vars; all have sensible defaults |
| `cover_art` | `CoverArtConfig` | `field(default_factory=CoverArtConfig)` | no env vars; all have sensible defaults |
| `essentia` | `EssentiaConfig` | `field(default_factory=EssentiaConfig)` | no env vars; `model_dir` defaults to `./models` |
| `max_workers` | `int` | `3` | hardcoded; matches `ThreadPoolExecutor(max_workers=3)` |
| `discogs_client` | `discogs_client.Client \| None` | `None` (created in `__post_init__`) | constructed from `discogs_token` and `user_agent` |

### Discogs client construction

```python
from dataclasses import dataclass, field
import discogs_client as _dc

@dataclass
class PipelineConfig:
    acoustid:  AcoustIDConfig  = field(default_factory=AcoustIDConfig)
    discogs:   DiscogsConfig   = field(default_factory=DiscogsConfig)
    itunes:    ItunesConfig    = field(default_factory=ItunesConfig)
    cover_art: CoverArtConfig  = field(default_factory=CoverArtConfig)
    essentia:  EssentiaConfig  = field(default_factory=EssentiaConfig)
    max_workers: int = 3
    discogs_client: object = field(init=False, default=None)

    def __post_init__(self):
        token = self.discogs.discogs_token
        ua    = self.discogs.user_agent
        if token:
            self.discogs_client = _dc.Client(ua, user_token=token)
        else:
            self.discogs_client = _dc.Client(ua)
```

The client is created once per `PipelineConfig` instance (typically once per batch session). It is passed to `fetch_discogs_metadata()` as the `client` argument on every call.

---

## Test Plan

### Test structure

```
backend/tests/test_importer/
    test_pipeline_merge.py      # unit: _build_db_row, resolved fields, column mapping
    test_pipeline_skip.py       # unit: hash check, mtime check, skip logic
    test_pipeline_db.py         # integration: upsert, id preservation, foreign keys
    test_pipeline_e2e.py        # slow: real file, mocked network; @pytest.mark.slow
    test_pipeline_concurrency.py # concurrency: same file twice, order assertions
```

### Unit tests — mocked importers (`test_pipeline_merge.py`)

Use `unittest.mock.patch` to replace each importer function. No filesystem reads except for the test fixture file.

**Test: resolved field fallback priority**
```python
from unittest.mock import patch, MagicMock

def test_resolved_year_uses_mb_first(tmp_path):
    """MB year wins over Discogs year and tags."""
    fake_file = tmp_path / "track.mp3"
    fake_file.write_bytes(b"fake")
    with patch("backend.importer.pipeline.read_tags") as mt, \
         patch("backend.importer.pipeline.identify_track") as ma, \
         patch("backend.importer.pipeline.fetch_discogs_metadata") as md, \
         patch("backend.importer.pipeline.fetch_itunes") as mi, \
         patch("backend.importer.pipeline.fetch_cover_art") as mc, \
         patch("backend.importer.pipeline._hash_file", return_value="abc"), \
         patch("backend.importer.pipeline._is_essentia_available", return_value=False):
        mt.return_value = {"tag_year_id3v24": "2001", ...}
        ma.return_value = {"year": 2003, "title": "T", "artist": "A", ...}
        md.return_value = {"discogs_year": 2002, ...}
        mi.return_value = {"itunes_release_date": "2000-01-01T00:00:00Z", ...}
        mc.return_value = {"cover_art_url": None, ...}
        db = get_db(":memory:")
        result = import_track(str(fake_file), db, PipelineConfig())
    assert result["resolved_year"] == 2003
```

**Tests to write:**
1. `test_resolved_year_priority` — MB > Discogs > Discogs master > tag_id3v24 > tag_id3v23 > iTunes
2. `test_resolved_title_falls_back_to_stem` — all sources None → filename stem
3. `test_resolved_key_uses_essentia` — Essentia key+scale combined correctly
4. `test_resolved_bpm_casts_tag_string` — `"128.0"` tag_bpm → `128.0` float
5. `test_hash_hit_skips_all_importers` — pre-insert a row with matching mtime; assert no importer called
6. `test_empty_acoustid_does_not_abort` — acoustid returns `{}` → pipeline continues, writes row
7. `test_essentia_skipped_when_unavailable` — patch `_ESSENTIA_AVAILABLE = False`; assert `analyse_track` not called
8. `test_discogs_error_dict_merged_safely` — discogs returns `_failure_dict()`; assert row written
9. `test_resolved_artwork_url_itunes_wins_over_caa` — both present; assert iTunes URL wins

### Integration test — real DB, mocked network (`test_pipeline_db.py`)

```python
import pytest
from backend.database import get_db
from backend.importer.pipeline import import_track, PipelineConfig
from pathlib import Path

FIXTURE = Path(__file__).parent.parent / "fixtures" / "short.mp3"

@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_full_pipeline_writes_row(tmp_path):
    db = get_db(tmp_path / "test.db")
    config = PipelineConfig(...)  # with network importers mocked

    with patch("backend.importer.pipeline.identify_track", return_value={}), \
         patch("backend.importer.pipeline.fetch_discogs_metadata", return_value={}), \
         patch("backend.importer.pipeline.fetch_itunes", return_value={}), \
         patch("backend.importer.pipeline.fetch_cover_art", return_value={}):
        result = import_track(str(FIXTURE), db, config)

    assert result is not None
    row = db.execute("SELECT * FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()
    assert row is not None
    assert row["resolved_title"] is not None  # at minimum: filename stem

def test_upsert_preserves_id(tmp_path):
    """Re-importing a changed file must not change the track's id."""
    db = get_db(tmp_path / "test.db")
    # First import
    import_track(str(FIXTURE), db, config)
    row1 = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()

    # Force re-import by clearing the stored mtime
    db.execute("UPDATE tracks SET file_modified_at = '0' WHERE file_path = ?", (str(FIXTURE),))
    db.commit()

    import_track(str(FIXTURE), db, config)
    row2 = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()

    assert row1["id"] == row2["id"]

def test_crate_membership_survives_reimport(tmp_path):
    """crate_tracks row must not be deleted on re-import (no INSERT OR REPLACE)."""
    db = get_db(tmp_path / "test.db")
    import_track(str(FIXTURE), db, config)
    track_id = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()["id"]

    db.execute("INSERT INTO crates(id, name, description) VALUES ('c1', 'Test', 'desc')")
    db.execute("INSERT INTO crate_tracks(crate_id, track_id) VALUES ('c1', ?)", (track_id,))
    db.commit()

    db.execute("UPDATE tracks SET file_modified_at = '0' WHERE file_path = ?", (str(FIXTURE),))
    db.commit()
    import_track(str(FIXTURE), db, config)

    count = db.execute("SELECT COUNT(*) FROM crate_tracks WHERE track_id = ?", (track_id,)).fetchone()[0]
    assert count == 1  # not deleted
```

### Concurrency test (`test_pipeline_concurrency.py`)

```python
import threading

def test_same_file_imported_twice_concurrently(tmp_path):
    """Only one DB row should exist after two concurrent import_track() calls."""
    db = get_db(tmp_path / "test.db")
    results = []
    errors = []

    def run():
        try:
            r = import_track(str(FIXTURE), db, config)
            results.append(r)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors
    count = db.execute("SELECT COUNT(*) FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()[0]
    assert count == 1
```

### Fixtures

- `backend/tests/fixtures/short.mp3` — a short (5–10 second) MP3 with ID3 tags. Check this into the repo. Generate with: `ffmpeg -f lavfi -i sine=frequency=440:duration=5 -codec:a libmp3lame -b:a 128k short.mp3`

### No live network calls

All network importers (`identify_track`, `fetch_discogs_metadata`, `fetch_itunes`, `fetch_cover_art`) are mocked in every test. AcoustID, MusicBrainz, Discogs, iTunes, and CAA are never contacted in tests.

---

## Open Questions

1. **`discogs_styles_search` column**: The DB schema has this column but `discogs.py` does not return it. **Resolved above**: compute it in `_build_db_row()` as `" ".join(json.loads(discogs.get("discogs_styles") or "[]"))`. This is a space-joined plain-text version for potential full-text search.

2. **`es_genre_top_labels_search` column**: Same pattern. **Resolved above**: compute as `" ".join(essentia.get("genre_top_labels") or [])` in `_build_db_row()`.

3. **`embedding` from Essentia vs sentence-transformers**: `essentia_analysis.py` returns `embedding` (the Discogs-EffNet embedding, 1280-dim) in its dict. The DB schema has `vec_tracks.embedding FLOAT[1280]`. The plan specifies using sentence-transformers on resolved text fields. **Decision**: use the Essentia EffNet embedding (`essentia.get("embedding")`) when available (WSL2); fall back to sentence-transformers when Essentia is unavailable. This avoids requiring sentence-transformers as a dependency for WSL2 runs. If both are None, skip the vec_tracks write. This decision should be confirmed before implementing Step 9.

4. **`embedding_track`, `embedding_artist`, `embedding_label`, `embedding_release`**: Returned by essentia but not in the current `tracks` or `vec_tracks` schema. **Decision**: omit from this pipeline implementation. These can be added in a future schema migration if needed.

5. **Thread safety of `discogs_client.Client` in concurrent batch imports**: If `import_tracks()` is ever parallelised (e.g. with a per-path ThreadPoolExecutor at the batch level), the Discogs client must not be shared across threads. For now, `import_tracks()` is sequential, so this is not a concern.

6. **`mb_genres` and `mb_tags` serialisation format**: Use `json.dumps()`, not `str()`. `str([])` is not round-trippable. `json.dumps([])` produces valid JSON `"[]"` that can be parsed back.

7. **`file_hash` algorithm stability**: If MD5 is ever changed to SHA-256, all stored hashes become invalid. Consider storing `"md5:" + hexdigest` to allow future migrations. Out of scope for the initial implementation — document it as a known future risk.

---

## Implementation Order

Build and test each step independently before moving to the next.

**Step 1 — Module scaffold**
Create `backend/importer/pipeline.py` with:
- Module docstring
- Imports (logging, hashlib, os, pathlib, concurrent.futures, sqlite3, json, datetime)
- `logger = logging.getLogger(__name__)`
- `_ESSENTIA_AVAILABLE` detection at module level
- Stub implementations of all public functions (raise `NotImplementedError`)
- `PipelineConfig` added to `backend/config.py`

**Step 2 — `_hash_file()` and `_check_skip()`**
Implement and unit-test the hash and mtime skip logic.
Tests: `test_pipeline_skip.py` — new file, unchanged file (mtime match), changed mtime but same hash, changed hash.

**Step 3 — `_build_db_row()` — column mapping only (no resolved fields)**
Implement the column mapping from each importer's return dict to DB column names. Use fixed dicts as inputs. Assert all 170+ column keys are present in the output.
Tests: `test_pipeline_merge.py` — feed fixed importer dicts; assert output keys match `_TRACKS_COLUMNS`.

**Step 4 — Resolved field computation**
Add resolved field logic to `_build_db_row()`.
Tests: all nine resolved-field unit tests listed above.

**Step 5 — `_TRACKS_COLUMNS` list and `_INSERT_SQL` string**
Build the INSERT SQL from the column list. Verify it parses without error. No test needed beyond the integration test.

**Step 6 — `import_track()` — main orchestration**
Implement the full pipeline body: hash check → tags → executor → Discogs → CAA → `_build_db_row()` → INSERT. All importers mocked in tests.
Tests: integration tests in `test_pipeline_db.py` — row written, UPSERT preserves id, crate membership survives re-import.

**Step 7 — Error handling hardening**
Add `_TrackLogger`, per-event log calls at correct levels, `try/except` wrapping the SQLite write.
Tests: test that a failed importer (returns `{}`) does not abort the pipeline; test that a SQLite write failure (mock `db.execute` to raise) returns `None` without raising.

**Step 8 — `import_tracks()` batch entry point**
Implement with `on_progress` callback. No new tests needed beyond calling `import_track()` in a loop.

**Step 9 — Embedding write (optional, after Open Question 3 is resolved)**
Implement vec_tracks DELETE + INSERT after the tracks UPSERT. Gated on `_VEC_AVAILABLE` from `database.py`. Tests: assert `vec_tracks` row written when Essentia embedding is available.

**Step 10 — `test_pipeline_concurrency.py`**
Write and run the same-file-twice concurrency test. Confirm only one row exists.

**Step 11 — `scripts/import_library.py`**
Write the batch entry point script with `tqdm` progress bar, file discovery (walk folder, filter by extension), and `import_tracks()` call. This is a script, not a module — not unit-tested.
