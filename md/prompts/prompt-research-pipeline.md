# Task: Research and Document the Import Pipeline Design

## Context

Read CLAUDE.md and CURRENT_STATE.md before starting. This is Phase 2 research —
the goal is to produce a reference document that answers every design question
needed before writing `backend/importer/pipeline.py`.

All six importers already exist and are validated:

| Importer | Entry point | Inputs | Returns |
|---|---|---|---|
| `tags.py` | `read_tags(path)` | file path | flat dict, `tag_*` fields |
| `acoustid.py` | `identify_track(path, config)` | file path | flat dict, `acoustid_*` / `mb_*` fields |
| `discogs.py` | `fetch_discogs_metadata(artist, title, label, catno, barcode, year, client, config)` | from tags + MB | flat dict, `discogs_*` fields |
| `itunes.py` | `fetch_itunes(artist, title, duration_seconds, config)` | from tags | flat dict, `itunes_*` fields |
| `cover_art.py` | `fetch_cover_art(release_mbid, release_group_mbid, config, mb_has_front_art)` | from acoustid/MB | flat dict, `caa_*` fields |
| `essentia_analysis.py` | `analyse_track(path, config)` | file path | flat dict, `es_*` fields + embedding |

The database schema is in `backend/database.py`. The resolved field fallback chains
are documented in CLAUDE.md under "Resolved field fallback chains".

`pipeline.py` does not exist yet. This research document will be the basis for its
implementation plan.

---

## What to research

### 1. Python concurrency primitives for I/O-bound + CPU-bound mixed workloads

The pipeline runs importers in mixed modes:
- `read_tags()` — instant, no I/O beyond the file open
- `identify_track()` — network I/O (AcoustID + MusicBrainz, sequential internally)
- `fetch_itunes()` — network I/O
- `fetch_discogs_metadata()` — network I/O
- `fetch_cover_art()` — network I/O
- `analyse_track()` — CPU-bound (Essentia, WSL2 only)

Research the following from Python documentation and community sources:

**ThreadPoolExecutor**
- Exact import path and constructor parameters
- How `submit()` works vs `map()` — which is appropriate for heterogeneous tasks with different inputs
- How to retrieve results from futures — `future.result()`, `as_completed()`, `wait()`
- How exceptions raised inside a submitted callable are propagated — what happens when you call `.result()` on a failed future
- The `shutdown(wait=True)` contract — does it guarantee all futures are complete?
- Whether `ThreadPoolExecutor` is safe for network I/O workloads (GIL considerations)

**Context managers**
- `with ThreadPoolExecutor(...) as executor:` — what happens to pending futures if the `with` block exits due to an exception?
- Whether futures submitted before the exception are cancelled or run to completion

**Timeout handling**
- How to set a per-future timeout using `future.result(timeout=N)`
- What exception is raised on timeout — exact type and import
- Whether timed-out futures continue executing in the background or are cancelled

**asyncio vs threading for this use case**
- Is there a reason to prefer `asyncio` for this pipeline? Document the trade-offs concisely.
- The importers are synchronous functions. What would be required to run them under asyncio?
- Recommendation: threading or asyncio for this pipeline, and why.

### 2. File hashing for change detection

The pipeline must skip files that have not changed since last import. The check is:
`file_path + file_hash already in DB, and file_modified_at matches`.

Research:
- The correct Python approach to hashing a large audio file (files can be 50–500 MB)
- `hashlib` — which algorithm is appropriate (MD5, SHA1, SHA256) for change detection
  where collision resistance is not needed but speed matters
- Whether reading the whole file into memory is required or if chunked hashing is possible
- Exact code pattern for chunked hashing with `hashlib`
- Whether `os.stat().st_mtime` is reliable on Windows NTFS and on WSL2 mounts of Windows paths
- Whether mtime alone is sufficient or whether hashing is also needed — when would they diverge?
- How to store mtime in SQLite — what format (ISO 8601, Unix timestamp float)

### 3. SQLite INSERT OR REPLACE semantics

`pipeline.py` will write all importer results via a single `INSERT OR REPLACE INTO tracks`.

Research from SQLite documentation:
- The exact semantics of `INSERT OR REPLACE` — when does it trigger, what does it delete/reinsert
- Whether `INSERT OR REPLACE` preserves the `id` (INTEGER PRIMARY KEY AUTOINCREMENT) of an existing row
  or assigns a new one — this matters for foreign keys in `crate_tracks` and `crate_corrections`
- Whether `INSERT OR REPLACE` fires `ON DELETE CASCADE` on dependent tables
- The alternative: `INSERT OR IGNORE` + `UPDATE` — when is this preferable?
- The `UPSERT` syntax (`INSERT ... ON CONFLICT DO UPDATE SET ...`) — SQLite version required,
  and whether it avoids the delete-reinsert problem
- Recommendation for the pipeline: which insert strategy to use and why

### 4. Partial results and error isolation

Each importer returns a flat dict and never raises. The pipeline must:
- Accept partial results (any importer can return an empty or error-flagged dict)
- Still write a row to the database even if all network importers fail
- Log which importers failed per track without aborting the batch

Research:
- The Python `logging` module — best practice for per-track structured logging
  (how to include file path and importer name in every log line without repeating them)
- `logging.LoggerAdapter` — what it is, when it's useful for this pattern
- Whether to use a single logger for the whole pipeline or per-module loggers —
  document the standard Python convention

### 5. Essentia availability detection

Essentia only works in WSL2. The pipeline must detect whether it is running in
WSL2 and skip `analyse_track()` gracefully if not.

Research:
- How to reliably detect WSL2 at runtime in Python (reading `/proc/version`, environment
  variables, or other signals)
- Whether a simple `try: import essentia` guard is sufficient or whether the import
  succeeds on Windows but the algorithms fail at runtime
- How to make the skip visible in logs without being noisy on every track

### 6. Progress reporting for batch imports

The pipeline will be called on potentially thousands of tracks. The caller (a CLI
script or FastAPI background task) needs to know progress.

Research:
- The standard Python pattern for progress callbacks in a library function —
  `callable` argument vs `queue.Queue` vs generator/yield
- How `tqdm` integrates with `ThreadPoolExecutor` — whether it works with futures
- Whether to couple `tqdm` to `pipeline.py` or keep it in the calling script
- Recommendation: how `pipeline.py` should expose progress to its caller

### 7. Config object design

Each importer takes a config object (`AcoustIDConfig`, etc.). The pipeline needs
to pass the right config to each importer.

Research:
- Whether to accept one config object per importer or a single unified config object
- Python `dataclasses` vs `pydantic.BaseModel` for config — trade-offs for this use case
- How `backend/config.py` currently defines configs (read the file before answering)
- Whether environment variable loading should live in the config class or outside it

### 8. Embedding generation timing

`analyse_track()` currently returns Essentia features. Embeddings (sentence-transformers)
are a separate step that needs a resolved text string (e.g. artist + title + label + genre).

Research:
- Whether embeddings should be computed inside `pipeline.py` after the merge step,
  or in a separate `embeddings.py` call
- When the resolved fields are available — they can only be computed after all importers
  have returned and the merge is done
- How `sqlite-vec` stores vector data — the column type, the insert syntax, and whether
  it is part of the same `INSERT OR REPLACE` statement or a separate write

Research `sqlite-vec` from its documentation and source:
- The exact SQL to create a vector column or virtual table
- The exact Python insert syntax for a vector value (does it take a list, bytes, numpy array?)
- Whether `INSERT OR REPLACE` works on the vec virtual table or requires a separate upsert

### 9. Resolved field computation

After all importers return, the pipeline must compute the `resolved_*` fields using
the fallback chains defined in CLAUDE.md.

Research the correct Python pattern for expressing a fallback chain:
- `next((v for v in [a, b, c] if v), None)` — does this handle empty strings correctly?
- Whether `None` and `""` should be treated identically in the fallback chain
- How to handle the `resolved_year` chain which requires slicing (`[:4]`) on string values
  that may be `None`
- Write out the resolved field logic as pseudocode for each field — this will be copied
  directly into the implementation plan

### 10. Test strategy for `pipeline.py`

Research the correct approach to unit testing the pipeline given that it calls six
importers and writes to SQLite.

Research:
- Whether to mock individual importers with `unittest.mock.patch` or test with real
  importers against a real file
- How `pytest` fixtures work with temporary SQLite databases — the `tmp_path` fixture
- The difference between integration tests (real importers, real file) and unit tests
  (mocked importers, assert merge logic) — which is more valuable here and why
- How to test the concurrency logic without relying on wall-clock timing

---

## Files to read before writing the document

Read these files in full before writing your research document:

- `backend/importer/tags.py` — understand the exact return dict structure
- `backend/importer/acoustid.py` — understand the return dict and config object
- `backend/importer/discogs.py` — understand the inputs and return dict
- `backend/importer/itunes.py` — understand the inputs and return dict
- `backend/importer/cover_art.py` — understand the inputs and return dict
- `backend/importer/essentia_analysis.py` — understand the return dict and config object
- `backend/config.py` — understand how configs are currently defined
- `backend/database.py` — understand the schema and the `get_db()` interface

---

## Output format

Write your findings as a single Markdown document saved to:

```
md/research/research-pipeline.md
```

Structure it as follows:

```
# Import Pipeline Research

## Sources
Links to every documentation page, library reference, or community source consulted.

## Concurrency Design
ThreadPoolExecutor vs asyncio decision. Exact execution order with concurrency
diagram. How futures are submitted, awaited, and timed out. Exception propagation.

## File Hashing and Change Detection
Algorithm choice, chunked hashing pattern, mtime reliability, SQLite storage format.

## SQLite Insert Strategy
INSERT OR REPLACE vs UPSERT — decision and exact SQL pattern to use.
Impact on AUTOINCREMENT ids and foreign keys.

## Partial Results and Error Isolation
How failed importers are handled. Logging pattern.

## Essentia Availability Detection
WSL2 detection method. How the skip is handled and logged.

## Progress Reporting
How pipeline.py exposes progress to its caller.

## Config Object Design
Single unified config vs per-importer configs. Current config.py pattern.

## Embedding Generation
Where embeddings are computed. sqlite-vec insert syntax.

## Resolved Field Logic
Pseudocode for every resolved_* field. Fallback chain implementation pattern.

## Test Strategy
Unit test approach for merge logic. Integration test approach for full pipeline.
Fixtures and mocking strategy.

## Open Questions
Anything that cannot be confirmed from documentation and needs a real test.
```

---

## Definition of done

- [ ] `md/research/research-pipeline.md` exists and is written from primary sources
- [ ] All eight importer files and config.py have been read before writing
- [ ] Concurrency section makes a clear recommendation (threading vs asyncio) with reasoning
- [ ] SQLite insert strategy section makes a clear recommendation with the exact SQL pattern
- [ ] Resolved field pseudocode covers every `resolved_*` field in the schema
- [ ] WSL2 detection method is documented with exact Python code
- [ ] sqlite-vec insert syntax is confirmed from documentation (not assumed)
- [ ] Test strategy section recommends a specific approach for both unit and integration tests
- [ ] All sources are linked so findings can be verified
- [ ] Open questions are listed explicitly
