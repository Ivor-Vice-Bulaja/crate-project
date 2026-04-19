# Task: Plan the Import Pipeline Orchestrator

## Context

Read CLAUDE.md and CURRENT_STATE.md before starting. This is a planning task — no
code is written here. The output is a detailed implementation plan for
`backend/importer/pipeline.py`.

All research is complete. Read the following files in full before writing the plan:

- `md/research/research-pipeline.md` — concurrency design, SQLite insert strategy, WSL2
  detection, resolved field pseudocode, and test strategy. All implementation
  decisions in this plan must be grounded in this document.
- `backend/importer/tags.py` — exact return dict, no config needed
- `backend/importer/acoustid.py` — exact return dict, config object signature
- `backend/importer/discogs.py` — exact inputs (artist, title, label, catno,
  barcode, year, client, config) and return dict
- `backend/importer/itunes.py` — exact inputs (artist, title, duration_seconds,
  config) and return dict
- `backend/importer/cover_art.py` — exact inputs (release_mbid, release_group_mbid,
  config, mb_has_front_art) and return dict; depends on acoustid output
- `backend/importer/essentia_analysis.py` — exact return dict, WSL2-only constraint
- `backend/config.py` — how configs are currently defined; whether to keep them
  separate or introduce a unified PipelineConfig
- `backend/database.py` — schema, `get_db()` interface, exact column list for
  the `tracks` table INSERT

**Core principle:** `pipeline.py` is the glue layer. It calls importers in the
correct order, merges their flat dicts, computes resolved fields, and writes one
row per track. It does not parse, score, or derive anything — that belongs in the
importers or in later pipeline stages. The pipeline never raises; it logs failures
and continues.

---

## What to plan

### 1. Module interface

Define the public API of `pipeline.py`. At minimum:

```python
def import_track(
    file_path: str | Path,
    db: sqlite3.Connection,
    config: ...,          # decide: unified or per-importer configs
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    ...
```

Specify:
- The exact function signature, including config parameter design (unified
  `PipelineConfig` or a bundle of per-importer configs — reference the research doc's
  recommendation and `backend/config.py`'s existing pattern)
- Return value: what does the function return? (the merged dict? the track DB row?
  a status summary?)
- Whether a batch entry point `import_folder(folder_path, ...)` belongs in this file
  or in a separate calling script
- Error contract: the function never raises — confirm this and state what it returns
  on total failure

### 2. Change detection (hash check)

Before running any importer, check whether the file has already been imported
and is unchanged.

Specify:
- The exact Python pattern for chunked SHA-1 hashing (reference the research doc's
  confirmed pattern — do not invent a new one)
- How mtime is read (`os.stat().st_mtime`) and stored (Unix float in the DB)
- The exact SQL query to check whether `(file_path, file_hash)` already exists in
  `tracks` with a matching `file_modified_at`
- What to return immediately on a cache hit (skip all importers)
- Whether to rehash on mtime change before comparing the hash, or always hash first

### 3. Execution order and concurrency

The pipeline must follow this fixed execution order from CLAUDE.md:

```
Step 1  hash check          — skip if unchanged (no importer calls)
Step 2  read_tags()         — instant; provides inputs for Discogs + iTunes
Step 3  concurrently:
          a. identify_track()        — network (AcoustID + MB)
          b. fetch_itunes()          — network; inputs from step 2
          c. analyse_track()         — CPU/WSL2; skip gracefully if unavailable
Step 4  fetch_discogs_metadata()     — inputs from steps 2 + 3a; after both complete
Step 5  fetch_cover_art()            — inputs from step 3a; after acoustid complete
Step 6  compute resolved_* fields
Step 7  INSERT OR REPLACE INTO tracks
```

Specify:
- How to submit step 3 tasks to `ThreadPoolExecutor(max_workers=3)` using `submit()`
- How to collect step 3 results — use `future.result(timeout=N)` for each future;
  what timeout value (reference research doc)
- What happens when a step 3 future times out — which fields default to empty dict,
  does step 4 still run with degraded inputs
- How to extract the inputs for step 4 from the acoustid result (which keys provide
  artist, title, label, catno, barcode, year — reference the acoustid return dict)
- How to extract the inputs for step 5 from the acoustid result (which keys provide
  release_mbid, release_group_mbid, mb_has_front_art)
- Whether step 4 and step 5 run concurrently with each other or sequentially;
  both depend on step 3a so they cannot start before it, but they are independent
  of each other — make a recommendation
- Whether the `discogs_client.Client` instance is created inside `pipeline.py` or
  passed in from outside; address thread safety (reference research doc)

### 4. Essentia availability detection

`analyse_track()` only works in WSL2. The pipeline must skip it gracefully on
native Windows.

Specify:
- The exact Python detection method (reference the research doc — reading
  `/proc/version` or equivalent)
- Where the detection lives: at module import time, at `import_track()` call time,
  or as a one-time check cached at startup
- How the skip is logged (once at startup, not per track)
- What the step 3c future returns when Essentia is skipped (empty dict with a
  sentinel field, or simply skip submitting the future)

### 5. Merging importer results

After all importers return, the pipeline merges seven flat dicts into one. Each
importer dict uses namespaced keys (`tag_*`, `mb_*`, `discogs_*`, etc.) so there
are no key conflicts.

Specify:
- The merge order (which dict "wins" on a key conflict — there should not be any,
  but define the fallback)
- How to handle a failed importer — its dict will be empty or contain only error
  fields; confirm that merging an empty dict is safe
- Whether to validate the merged dict against the DB schema (e.g. check all
  required columns are present) or trust the importers

### 6. Resolved field computation

After merging, compute the `resolved_*` fields using the fallback chains from
CLAUDE.md. The research doc has pseudocode for each field — copy it here and
translate it to exact Python expressions.

For each resolved field, specify:
- The fallback chain in order (first non-null, non-empty value wins)
- How to handle `None` vs `""` (treat them identically — an empty string is not
  a valid value)
- The exact Python one-liner for each field; for example:

```python
resolved_title = next(
    (v for v in [mb_title, tag_title, file_stem] if v),
    file_stem  # guaranteed non-null fallback
)
```

Cover every `resolved_*` field in the schema:
`resolved_title`, `resolved_artist`, `resolved_bpm`, `resolved_key`,
`resolved_label`, `resolved_year`, `resolved_artwork_url`

Note the `[:4]` slicing needed for year fields — handle None safely.

### 7. SQLite write

After resolving fields, write the row with a single INSERT statement.

Specify:
- Whether to use `INSERT OR REPLACE` or the UPSERT syntax
  (`INSERT ... ON CONFLICT DO UPDATE SET ...`) — reference the research doc's
  recommendation and its reasoning about AUTOINCREMENT id preservation
- The exact SQL pattern (write it out — do not leave it as "use the appropriate
  INSERT")
- How to pass the merged + resolved dict as parameters — named parameters (`:key`)
  or positional (`?`) — and how to build the parameter dict from the merged dict
- Whether embeddings are written in the same INSERT or a separate write; if
  separate, when and how (reference the research doc's sqlite-vec findings)
- How `file_hash`, `file_modified_at`, and `file_path` are added to the merged
  dict before the INSERT (they come from the hash check step, not from any importer)
- What to log on a successful write (track path + resolved_title at INFO level)

### 8. Error handling and logging

The pipeline must never abort a batch due to a single track failure. Each importer
already returns a dict (never raises). The pipeline layer must handle any remaining
failure modes.

Specify:
- What to do if `read_tags()` fails (it should not raise, but if it returns an
  empty dict with no `tag_title`, can the pipeline still proceed?)
- What to do if the SQLite write fails (log at ERROR, skip the track, continue batch)
- Whether to use `logging.LoggerAdapter` for per-track context (file path) — the
  research doc covers this; make a decision
- Logger naming: one logger (`backend.importer.pipeline`) or inherited from a
  root logger
- What is written to the log on each of: hash hit (DEBUG), importer timeout
  (WARNING), importer error flag in result dict (WARNING), successful write (INFO),
  write failure (ERROR)

### 9. Progress reporting

For batch imports of 5,000–20,000 tracks, the caller needs progress signals.

Specify:
- The progress callback signature: `callback(status: str, current: int, total: int)`
  or simpler — what is the minimum useful interface?
- When the callback is called: before hash check, after write, or both?
- Whether `tqdm` integration belongs in `pipeline.py` or in the calling script —
  reference the research doc's recommendation
- What the batch entry point (`import_folder` or equivalent) looks like if it lives
  in this file: does it discover files, check extensions, and call `import_track()`
  in a loop?

### 10. Config design

Specify the exact config object(s) the pipeline needs.

- Review `backend/config.py`'s current pattern before deciding
- If introducing a `PipelineConfig`, list every field it contains, its type, its
  default, and where it reads from (env var name)
- If keeping per-importer configs separate, specify how the pipeline receives and
  passes them (a named tuple? a simple namespace? individual arguments?)
- The Discogs client instance: created in `PipelineConfig.__post_init__`? Created
  lazily in `import_track()`? Passed in by the caller?

### 11. Test plan

Describe the tests for `backend/tests/test_importer/test_pipeline.py`.

- **Unit tests (mocked importers):** patch each importer function with
  `unittest.mock.patch`. The mocked importers return fixed dicts. Assert:
  - Correct merge output given known importer returns
  - Resolved field fallback chains work correctly (test each field with missing
    upstream values)
  - Hash hit causes all importers to be skipped (verify no importer is called)
  - Failed importer (returns empty dict) does not abort the pipeline
  - Essentia skipped when not in WSL2 (mock the detection function)
- **Integration test (real file, real DB):** use `tmp_path` for the SQLite file.
  Use a real audio file fixture (a short MP3 or WAV checked into
  `backend/tests/fixtures/`). Mock only the network importers. Assert that a row
  is written to the DB with the correct `file_path` and non-null `resolved_title`.
- **No live network calls in any test.** AcoustID, MusicBrainz, Discogs, iTunes,
  Cover Art Archive must all be mocked.
- **Concurrency test:** submit the same file path twice concurrently; assert only
  one DB row exists after both calls complete.

### 12. Implementation order

Number the steps to build this module from scratch. Be concrete — each step should
be buildable and testable independently before moving to the next.

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/plan-pipeline.md
```

Structure:

```
# Implementation Plan: Import Pipeline Orchestrator

## Overview
One paragraph: what pipeline.py does, what it delegates, what it guarantees.

## Module Interface
Exact function signatures. Return type. Error contract.

## Change Detection
Hash algorithm, chunked pattern, mtime storage, SQL check query.

## Execution Order and Concurrency
Diagram + prose. ThreadPoolExecutor setup. Future submission and collection.
Timeout values. Degraded-input handling for downstream importers.

## Essentia Availability
Detection method. Skip behaviour. Logging strategy.

## Merge Strategy
Dict merge order. Empty dict handling. Key conflict policy.

## Resolved Field Computation
Python one-liner for every resolved_* field.

## SQLite Write
Exact INSERT pattern. Parameter dict construction. Embeddings timing.

## Error Handling and Logging
Per-failure-mode strategy. Logger naming. LoggerAdapter decision.

## Progress Reporting
Callback signature. tqdm placement. Batch entry point (if in this file).

## Config Design
PipelineConfig fields table: field | type | default | env var.
Discogs client construction.

## Test Plan
Unit tests (mocked importers). Integration test. Concurrency test.
Fixtures and mock strategy.

## Open Questions
Anything not answerable from the research doc or existing importer code.

## Implementation Order
Numbered steps.
```

---

## Definition of done

- [ ] `md/plans/plan-pipeline.md` exists
- [ ] All eight source files listed above have been read before writing the plan
- [ ] Execution order section matches the canonical order in CLAUDE.md exactly
- [ ] Concurrency section specifies `ThreadPoolExecutor(max_workers=3)`, exact
      `submit()` calls, and timeout handling for each step 3 future
- [ ] Resolved field section has a Python expression for every `resolved_*` field
      in the schema with None-safe fallback handling
- [ ] SQLite write section specifies the exact INSERT pattern (not "use appropriate INSERT")
      and addresses AUTOINCREMENT id preservation
- [ ] Essentia skip section specifies the exact detection method from the research doc
- [ ] Config section lists every config field with its env var name and default
- [ ] Test plan specifies no live network calls and covers hash-hit skip, empty importer
      dict, and concurrency
- [ ] Implementation order is a concrete numbered list of buildable steps
- [ ] No design decisions are left vague — every "decide X or Y" question has a stated answer
