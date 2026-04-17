# Task: Research SQLite Schema Design for Crate

## Context

Read CLAUDE.md before starting. This task is Phase 1 research — no application code
is written here. The goal is to produce a complete, accurate reference document that
will be used to finalise the database schema and implement `backend/database.py` in
Phase 2.

Crate is a local DJ library application. Every track is enriched by up to 6 importers
(mutagen, AcoustID/MusicBrainz, Discogs, iTunes, Cover Art Archive, Essentia). All
importer outputs must be persisted to SQLite. Downstream stages (API filtering,
vector search, crate fill) read from this database — it must contain everything they
could ever need.

**Schema follows data, not the other way around.** The importer output fields are
already confirmed and documented. This research task is about how to store them
correctly in SQLite — not what to store.

---

## What to research

### 1. SQLite data types and type affinity

Research SQLite's actual type system — it is not what most people expect:

- The five storage classes: NULL, INTEGER, REAL, TEXT, BLOB — what each stores
- Type affinity rules — how SQLite coerces values when a column is declared `INTEGER`
  but a TEXT is inserted; when this causes silent data loss vs silent coercion
- Whether `BOOLEAN` is a real type in SQLite or a convention — how TRUE/FALSE are stored
- Whether `TIMESTAMP` is a real type — how datetime values are stored and queried
- The `NUMERIC` affinity — when it matters vs REAL
- JSON storage: is there a JSON type, or is it TEXT? What SQLite version introduced
  the `json_each` and `json_extract` functions, and what version ships on typical
  Linux/macOS/WSL2 systems?

### 2. sqlite-vec extension — vector similarity search

The CLAUDE.md design decision is SQLite + sqlite-vec for vector search (used in crate
fill Stage 2: embedding similarity). Research sqlite-vec specifically:

- What sqlite-vec is — who maintains it, what it does, GitHub URL
- How to install it — Python package name, how to load it into a connection at runtime
  (`conn.enable_load_extension` + `conn.load_extension`)
- How to declare a vector column — exact SQL syntax (e.g. `embedding FLOAT[1024]`)
- How to insert a vector — what Python type to pass, any serialisation step needed
- How to run a similarity query — exact SQL syntax for KNN search
- What distance metrics are supported (L2, cosine, dot product)
- Whether vec columns live in a separate virtual table or in the main table
- How vec indexes work — do they require a separate `CREATE VIRTUAL TABLE` call?
- What the Essentia EffNet embedding dimension is (check `backend/importer/essentia_analysis.py`)
  and confirm what shape sqlite-vec needs to store it
- Any known limitations: max dimension, max row count, thread safety

### 3. Schema structure options for a multi-source import pipeline

Three structural patterns are common when one entity (a track) is enriched by multiple
independent sources. Research the trade-offs of each in the context of SQLite and
Crate's actual query patterns (BPM/key/label filtering, vector search, crate fill):

**Option A — single wide table**
All importer outputs in one `tracks` table. Every row has ~100–150 columns, most NULL
for any given track.

**Option B — one table per importer source**
`tracks` (file identity only) + `track_tags` + `track_acoustid` + `track_discogs` +
`track_itunes` + `track_essentia`. Joined on `track_id`.

**Option C — hybrid**
`tracks` holds canonical resolved fields + file identity.
Raw importer outputs in per-source tables.
Resolved fields (`resolved_title`, `resolved_bpm`, etc.) computed by the pipeline
and written back to `tracks`.

For each option document: query complexity for common Crate queries, write complexity
for the pipeline, how re-import of a single source works, schema evolution when a new
importer is added. Conclude with a recommendation and reasoning.

### 4. JSON columns in SQLite

Several importer fields are arrays (Discogs styles, genres, tracklist; Essentia
genre_probabilities, instrument_probabilities, moodtheme_probabilities, etc.).
SQLite has no native array type. Research:

- The standard pattern for storing arrays in SQLite — JSON TEXT column
- `json_extract(col, '$.key')` and `json_each(col)` — exact syntax, SQLite version
  requirement, performance characteristics
- Whether to store both a raw JSON column AND a denormalised flat column for common
  query patterns (e.g. `discogs_styles TEXT` as JSON array +
  `discogs_styles_search TEXT` as space-separated for LIKE queries)
- When a junction table is better than a JSON column (e.g. if you need to query
  "all tracks with style = 'Dub Techno'" frequently)

### 5. Schema migration patterns in SQLite

The schema will evolve as new importers are added or fields change. Research:

- `PRAGMA user_version` — what it is, how to read and set it, how to use it for
  schema version tracking
- `ALTER TABLE ADD COLUMN` — what SQLite supports and what it does not (e.g. cannot
  add a column with a non-constant default, cannot remove columns in older SQLite)
- The standard pattern for a migration runner in Python: read user_version, compare
  to list of known migrations, apply in order, update user_version
- How to handle `:memory:` databases in tests — does `PRAGMA user_version` persist
  across connections in an in-memory database? (It does not — each connection is a
  fresh database)
- Whether WAL mode and foreign keys (already set in `get_db()`) interact with
  migrations in any unexpected way

### 6. SQLite indexes — what to index and why

Research what indexes matter for Crate's query patterns:

- How SQLite uses indexes — B-tree index, when the query planner uses vs ignores them
- UNIQUE indexes vs UNIQUE constraints — are they the same in SQLite?
- `EXPLAIN QUERY PLAN` — how to use it to verify an index is being used
- Which columns in a DJ library query are likely to be filtered: BPM range, key,
  label, year range, resolved_bpm, resolved_key
- Partial indexes — does SQLite support them? When are they useful (e.g. index only
  rows where `acoustid_match = 1`)?
- Whether a covering index matters at SQLite's scale for a 20,000-track library

### 7. BLOB storage for embeddings (fallback if sqlite-vec is not used)

In case sqlite-vec is not available at runtime, document the fallback:

- Storing float arrays as BLOB — how to serialise a numpy float32 array to bytes in
  Python (`array.tobytes()` or `numpy.ndarray.tobytes()`)
- How to deserialise back to numpy — `numpy.frombuffer(blob, dtype=numpy.float32)`
- Performance of full-table BLOB reads for brute-force cosine similarity in Python
  at 5,000–20,000 tracks — is it feasible as a fallback?
- Whether storing as JSON TEXT (list of floats) is readable/writable at acceptable
  speed vs BLOB

---

## What NOT to research

Do not design the actual schema column list here — that is done by reading the
confirmed importer output fields from the source files and research docs, which is
implementation work done in Phase 2. This research task is about the *mechanics*:
types, sqlite-vec, structure patterns, JSON columns, migrations, indexes.

Do not write any Python code. Do not write any SQL `CREATE TABLE` statements.
Document only findings and design decisions.

---

## Output format

Write your findings as a single Markdown document saved to:

```
docs/research/research-database-schema.md
```

Structure it as follows:

```
# Database Schema Research

## Sources
Links to every page, doc, or repository consulted.

## SQLite Type System
Storage classes, type affinity, BOOLEAN, TIMESTAMP, JSON.
What version of SQLite ships on WSL2/typical Linux — check with `sqlite3 --version`.

## sqlite-vec
What it is, install, load, declare vector column, insert, query.
Exact SQL syntax. Embedding dimension for Essentia EffNet. Known limitations.

## Schema Structure Options
Option A / B / C — trade-offs for Crate's query patterns.
Recommendation with reasoning.

## JSON Columns
Standard patterns. json_extract / json_each. Denormalisation trade-offs.
When a junction table is better.

## Schema Migration Pattern
PRAGMA user_version. ALTER TABLE limits. Migration runner design.
Interaction with :memory: test databases.

## Indexes
What SQLite indexes are, when the planner uses them.
Which columns to index for Crate. Partial indexes. EXPLAIN QUERY PLAN.

## BLOB Fallback for Embeddings
Serialisation, deserialisation, performance estimate for 20,000 tracks.

## Open Questions
Anything that cannot be confirmed from documentation alone.
```

---

## Definition of done

- [ ] `docs/research/research-database-schema.md` exists and covers all 7 research areas
- [ ] sqlite-vec install, load, declare, insert, and query are documented with exact
      syntax — not paraphrased
- [ ] The SQLite version available on WSL2 is confirmed (affects JSON function availability)
- [ ] All three schema structure options are evaluated against Crate's actual query
      patterns before a recommendation is made
- [ ] JSON column patterns are documented with `json_each` / `json_extract` syntax
- [ ] Migration pattern using `PRAGMA user_version` is documented
- [ ] BLOB serialisation/deserialisation for numpy float32 arrays is documented
- [ ] All sources are linked so findings can be verified
- [ ] No SQL `CREATE TABLE` statements are written — that is Phase 2 work
- [ ] No Python implementation code is written — that is Phase 2 work
