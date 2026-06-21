# Task: Write the Database Schema Implementation Plan

## Context

Read CLAUDE.md before starting. This is a Phase 2 planning task — its output is a step-by-step implementation plan for `backend/database.py` and the `tracks` table schema.

All research is complete. The following documents contain the confirmed facts that drive this plan:

- `md/research/research-database-schema.md` — SQLite types, sqlite-vec, schema structure options, JSON columns, migrations, indexes, BLOB fallback
- `md/research/research-acoustid.md` — confirmed AcoustID + MusicBrainz fields
- `md/research/research-discogs.md` — confirmed Discogs fields
- `md/research/research-mutagen.md` — confirmed file tag fields
- `md/research/research-essentia.md` — confirmed Essentia output fields
- `CLAUDE.md` sections: Data Sources, Database Schema (draft), Import Pipeline, Crate Fill Pipeline

Also read the existing importer implementations to confirm what each returns at runtime:

- `backend/importer/tags.py`
- `backend/importer/acoustid.py`
- `backend/importer/discogs.py`
- `backend/importer/itunes.py`
- `backend/importer/cover_art.py`
- `backend/importer/essentia_analysis.py`

The research document concluded that **Option A (single wide table)** is the right schema structure for Crate. That decision is settled — do not re-evaluate it here.

---

## What to plan

Produce an implementation plan for `backend/database.py`. This file is responsible for:

1. Opening and configuring the SQLite connection
2. Loading the sqlite-vec extension
3. Running schema migrations (using `PRAGMA user_version`)
4. Providing a `get_db()` function for use by the rest of the backend

The plan must also specify the complete `CREATE TABLE tracks (...)` statement column by column.

---

## Plan sections required

### 1. Column inventory

Read every importer source file and research document. For every field each importer returns, decide:

- Column name (use `source_fieldname` prefix convention: `tag_title`, `mb_recording_id`, `discogs_label`, `itunes_artwork_url`, `es_bpm`, etc.)
- SQLite type (`TEXT`, `REAL`, `INTEGER`, `BOOLEAN` stored as INTEGER)
- Whether it can be NULL (most importer fields can — match rate is not 100%)
- Whether it is a JSON array (Discogs styles, Essentia probability arrays, etc.)

Also include:

- File identity columns: `id`, `file_path`, `file_hash`, `file_size_bytes`, `file_modified_at`
- Resolved canonical columns: `resolved_title`, `resolved_artist`, `resolved_bpm`, `resolved_key`, `resolved_label`, `resolved_year`, `resolved_artwork_url` — these are computed by the pipeline from the fallback chain in CLAUDE.md
- Import status columns: `imported_at`, `acoustid_imported_at`, `mb_imported_at`, `discogs_imported_at`, `itunes_imported_at`, `essentia_imported_at` — timestamps for each importer run, NULL if not yet run
- Derived score columns: `energy_score`, `darkness_score`, `groove_score` — REAL, NULL until formulas are validated
- Usage columns: `last_played_at`, `play_count`

Specify which JSON columns also need a companion `_search` TEXT column for LIKE queries (e.g. `discogs_styles_search`).

### 2. Resolved field fallback chain

Document the exact fallback chain for each resolved field. Base it on the CLAUDE.md provisional chain, updated against confirmed source reliability from the research docs and batch test results:

- `resolved_bpm`: priority order, NULL condition
- `resolved_key`: priority order, NULL condition
- `resolved_title`: priority order, NULL condition
- `resolved_artist`: priority order, NULL condition
- `resolved_label`: priority order, NULL condition
- `resolved_year`: priority order, NULL condition
- `resolved_artwork_url`: priority order, NULL condition

### 3. Crate tables

These are already specified in CLAUDE.md and are stable. Include them in the plan verbatim:

- `crates` table
- `crate_tracks` table
- `crate_corrections` table

### 4. sqlite-vec virtual table

Specify the `CREATE VIRTUAL TABLE vec_tracks ...` statement. Use the confirmed EffNet embedding dimension from `backend/importer/essentia_analysis.py` and the confirmed distance metric from the research document.

### 5. Index definitions

List every `CREATE INDEX` statement. Use the index priority ranking from the research document:

- High-priority: `resolved_bpm`, `resolved_key`, `resolved_label`, `resolved_year`, `file_path` (UNIQUE), `file_hash`
- Medium-priority: `resolved_artist`, `resolved_title`, `acoustid_id`
- Partial indexes: `acoustid_id WHERE acoustid_id IS NOT NULL`, BPM+loudness WHERE essentia has run

### 6. `database.py` implementation steps

Step-by-step plan for implementing `backend/database.py`:

1. Connection setup — `sqlite3.connect()`, `row_factory = sqlite3.Row`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`
2. Extension loading — `conn.enable_load_extension(True)`, `sqlite_vec.load(conn)`, `conn.enable_load_extension(False)`. Handle `OperationalError` if sqlite-vec is unavailable (log warning, do not crash)
3. Migration runner — read `PRAGMA user_version`, apply pending migrations in order, update version after each
4. Migration 1 — `CREATE TABLE tracks (...)` with all columns from the column inventory
5. Migration 2 — `CREATE VIRTUAL TABLE vec_tracks ...`
6. Migration 3 — all index definitions
7. Migration 4 — crate tables (`crates`, `crate_tracks`, `crate_corrections`)
8. `get_db()` function — returns a configured connection; caller is responsible for closing it

### 7. Test plan

List the pytest test cases for `backend/tests/test_database.py`:

- Schema applies cleanly from version 0 to latest on a fresh `:memory:` database
- `PRAGMA user_version` equals the expected version after migration
- All expected tables exist (`SELECT name FROM sqlite_master WHERE type='table'`)
- `vec_tracks` virtual table exists (may be skipped if sqlite-vec not installed)
- `get_db()` returns a `sqlite3.Row`-producing connection
- Re-running migrations on an already-migrated database is idempotent (does not raise)

---

## Constraints

- Use the column name prefix convention consistently: `tag_*`, `mb_*`, `discogs_*`, `itunes_*`, `caa_*`, `es_*` (Essentia), `resolved_*`
- All importer columns are nullable — import failures must not prevent a row from existing
- `file_path` must be UNIQUE — it is the deduplication key
- Do not include columns for sources not yet researched (Last.fm, Deezer) — schema evolves via migrations
- The derived score columns (`energy_score`, `darkness_score`, `groove_score`) are included as nullable REALs — their formulas are not locked in yet
- sqlite-vec unavailability must be handled gracefully — the app must work without vector search if the extension cannot be loaded
- All timestamp columns use TEXT ISO 8601 format (not UNIX integers) — consistent with the research document recommendation
- Do not implement the pipeline resolution logic here — that belongs in `backend/importer/pipeline.py` (Phase 2)

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/plan-database-schema.md
```

Structure it as:

```
# Plan: Database Schema — backend/database.py

## Overview
One paragraph summary of what is being built and why.

## Column Inventory
Full table: column name | type | nullable | source | notes
Grouped by: file identity / tag fields / AcoustID / MusicBrainz / Discogs / iTunes /
Cover Art Archive / Essentia / derived scores / resolved fields / usage / import status

## Resolved Field Fallback Chains
Bullet list per resolved field.

## CREATE TABLE tracks (...)
The complete SQL statement, ready to paste.

## CREATE VIRTUAL TABLE vec_tracks ...
The sqlite-vec virtual table statement.

## Index Definitions
All CREATE INDEX statements.

## Crate Tables
The three crate SQL statements from CLAUDE.md.

## database.py — Implementation Steps
Numbered steps with code snippets where the pattern is non-obvious.

## Test Plan
Bullet list of test cases.

## Open Questions
Anything that must be decided before or during implementation.
```

---

## Definition of done

- [ ] `md/plans/plan-database-schema.md` exists
- [ ] Column inventory covers every field returned by every importer (verified against source files)
- [ ] Fallback chains are specified for all 7 resolved fields
- [ ] Complete `CREATE TABLE tracks (...)` SQL is included — no placeholder columns
- [ ] sqlite-vec virtual table statement uses confirmed 1280-dim float32 with cosine metric
- [ ] All index statements match the priority ranking from the research document
- [ ] `database.py` implementation steps are specific enough to code from directly
- [ ] Test plan covers schema version, table existence, idempotency, and `get_db()` behaviour
- [ ] No importer logic or pipeline orchestration is included — this plan covers `database.py` only
