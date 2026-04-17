# Database Schema Research

## Sources

- [SQLite Datatypes and Type Affinity](https://www.sqlite.org/datatype3.html)
- [SQLite JSON Functions (json1)](https://www.sqlite.org/json1.html)
- [SQLite ALTER TABLE](https://www.sqlite.org/lang_altertable.html)
- [SQLite PRAGMA user_version](https://www.sqlite.org/pragma.html#pragma_user_version)
- [SQLite Query Planner](https://www.sqlite.org/queryplanner.html)
- [SQLite Partial Indexes](https://www.sqlite.org/partialindex.html)
- [sqlite-vec GitHub (asg017)](https://github.com/asg017/sqlite-vec)
- [sqlite-vec Python integration](https://alexgarcia.xyz/sqlite-vec/python.html)
- [sqlite-vec KNN queries](https://alexgarcia.xyz/sqlite-vec/features/knn.html)
- [sqlite-vec API Reference](https://alexgarcia.xyz/sqlite-vec/api-reference.html)
- [How sqlite-vec Works — Stephen Collins](https://stephencollins.tech/posts/how-sqlite-vec-works-for-storing-and-querying-vector-embeddings)
- [Store numpy arrays in sqlite — Kaushik Ghose](https://kaushikghose.wordpress.com/2013/12/05/store-numpy-arrays-in-sqlite/)
- [numpy.ndarray.tobytes](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.tobytes.html)
- [numpy.frombuffer](https://numpy.org/doc/2.1/reference/generated/numpy.frombuffer.html)

---

## SQLite Type System

### SQLite version on WSL2 (confirmed)

```
$ python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'
3.45.1
```

SQLite 3.45.1 ships with the default Ubuntu packages on WSL2 as of 2026-04. This is well above the 3.9.0 threshold for JSON functions and the 3.41.0 threshold recommended for sqlite-vec.

### Five storage classes

SQLite stores every value in one of five storage classes — these are the only types that actually exist on disk:

| Storage class | What it stores |
|---|---|
| NULL | A null value |
| INTEGER | Signed integer; uses 0, 1, 2, 3, 4, 6, or 8 bytes depending on magnitude |
| REAL | 8-byte IEEE 754 float |
| TEXT | String in database encoding (UTF-8, UTF-16BE, or UTF-16LE) |
| BLOB | Binary data stored exactly as given; no coercion |

### Type affinity

Column type declarations are advisory, not enforced. SQLite derives an **affinity** from the declared type name using these rules (first match wins):

1. Name contains `"INT"` → INTEGER affinity
2. Name contains `"CHAR"`, `"CLOB"`, or `"TEXT"` → TEXT affinity
3. Name contains `"BLOB"` or no type specified → BLOB affinity (none)
4. Name contains `"REAL"`, `"FLOA"`, or `"DOUB"` → REAL affinity
5. Otherwise → NUMERIC affinity

Affinity determines what SQLite *tries* to convert a value to on insert. It does not prevent inserting a TEXT value into an INTEGER column — it just attempts conversion.

### BOOLEAN

**BOOLEAN is not a real type in SQLite.** Booleans are stored as integers:
- `0` = FALSE
- `1` = TRUE

As of SQLite 3.23.0, the keywords `TRUE` and `FALSE` are recognised as aliases for `1` and `0`. The column declaration `BOOLEAN` gets NUMERIC affinity (rule 5 above), which is fine for 0/1 values.

### TIMESTAMP / datetime

**TIMESTAMP is not a real type in SQLite.** Datetime values can be stored in three formats:

| Format | Storage class | Example |
|---|---|---|
| ISO 8601 string | TEXT | `'2024-03-15 14:22:00.000'` |
| Julian day number | REAL | `2460385.1` |
| Unix timestamp | INTEGER | `1710509160` |

The SQLite built-in date/time functions (`datetime()`, `strftime()`, etc.) work with all three formats. For Crate, **TEXT ISO 8601** is the right choice — human-readable, sortable as text, and unambiguous.

The column declaration `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` gives TEXT affinity and stores values like `'2024-03-15 14:22:00'`. This is the standard pattern.

**Important for ALTER TABLE:** `CURRENT_TIMESTAMP` is **not** valid as a default value when adding a column with `ALTER TABLE ADD COLUMN`. It is only valid in `CREATE TABLE`. This is a migration-relevant restriction — see the Schema Migration section.

### NUMERIC affinity and silent coercion

NUMERIC affinity converts text to INTEGER or REAL if it looks like a number:
- `'500.0'` inserted into a NUMERIC column is stored as INTEGER `500`
- `'3.0e+5'` → INTEGER `300000` (can be stored exactly as int)
- Large integers beyond 64-bit signed range → REAL, losing precision for values beyond ~9.2e18

**Silent data loss scenarios:**
- A TEXT value like `'1234567890123456789012'` (too large for int64) stored in a NUMERIC column becomes REAL and loses precision
- Non-numeric text in a NUMERIC column via mathematical operators converts to `0` or `0.0`
- TEXT-to-REAL preserves only ~15.95 significant digits

For Crate: use TEXT for all string fields (track titles, artist names, keys, catalogue numbers). Use REAL for floats. Use INTEGER for integers. Avoid NUMERIC affinity where the column will only ever hold strings.

### JSON

**There is no JSON type in SQLite.** JSON is stored as TEXT.

`json_extract()` and `json_each()` were introduced in **SQLite 3.9.0** (2015-10-14). SQLite 3.45.1 on WSL2 fully supports all JSON functions.

---

## sqlite-vec

### What it is

sqlite-vec is a vector search SQLite extension maintained by **Alex Garcia** (GitHub: asg017), with sponsorship from Mozilla Builders, Fly.io, Turso, and SQLite Cloud. It is the successor to sqlite-vss and provides vector storage and KNN similarity search inside SQLite.

GitHub: https://github.com/asg017/sqlite-vec

**Status:** Pre-v1 as of 2026-04. Expect breaking changes. SQLite ≥ 3.41 is recommended (3.45.1 on WSL2 satisfies this).

### Install

```
pip install sqlite-vec
```

Or via uv: `uv add sqlite-vec`

### Load at runtime

```python
import sqlite3
import sqlite_vec

conn = sqlite3.connect("crate.db")
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)
```

`sqlite_vec.load()` handles the `load_extension` call internally. Extensions must be loaded per-connection — every new `sqlite3.connect()` call requires this setup.

### Declare a vector column

Vectors live in a **separate virtual table** declared with `CREATE VIRTUAL TABLE ... USING vec0(...)`. They do **not** live in the main `tracks` table. The virtual table is linked to the main table via `rowid`.

```sql
CREATE VIRTUAL TABLE vec_tracks USING vec0(
    track_id INTEGER PRIMARY KEY,
    embedding FLOAT[1280] distance_metric=cosine
);
```

- `FLOAT[1280]` — 32-bit float vectors of dimension 1280
- `distance_metric=cosine` — sets the default metric for MATCH queries
- `track_id INTEGER PRIMARY KEY` — links to the `tracks` table `id`
- Other supported types: `INT8[N]` (int8 quantised), `BIT[N]` (binary, N must be divisible by 8)

### Insert a vector from Python

Two methods — both produce the same internal BLOB format:

**From a Python list (using serialize_float32):**
```python
from sqlite_vec import serialize_float32

embedding = [0.1, 0.2, ..., 0.n]  # 1280 floats
conn.execute(
    "INSERT INTO vec_tracks(track_id, embedding) VALUES (?, ?)",
    [track_id, serialize_float32(embedding)]
)
```

**From a NumPy array (pass directly, must be float32):**
```python
import numpy as np

embedding = np.array([...]).astype(np.float32)  # shape (1280,)
conn.execute(
    "INSERT INTO vec_tracks(track_id, embedding) VALUES (?, ?)",
    [track_id, embedding]
)
```

NumPy float64 arrays must be cast to float32 before passing. The Essentia EffNet model outputs float32 natively (the code in `essentia_analysis.py` returns `.tolist()` — convert back to `np.array(..., dtype=np.float32)` before inserting).

### KNN similarity query

```sql
-- MATCH syntax (preferred; uses vec0 index)
SELECT track_id, distance
FROM vec_tracks
WHERE embedding MATCH :query_vector
  AND k = 100;

-- LIMIT syntax (SQLite ≥ 3.41 only)
SELECT track_id, distance
FROM vec_tracks
WHERE embedding MATCH :query_vector
LIMIT 100;
```

To retrieve full track data, join back to the main table:

```sql
WITH knn AS (
    SELECT track_id, distance
    FROM vec_tracks
    WHERE embedding MATCH :query_vector
      AND k = 100
)
SELECT t.id, t.resolved_title, t.resolved_artist, knn.distance
FROM knn
LEFT JOIN tracks t ON t.id = knn.track_id
ORDER BY knn.distance;
```

Query vector must be passed as a serialised BLOB (same format as insert):
```python
from sqlite_vec import serialize_float32

results = conn.execute(
    "SELECT track_id, distance FROM vec_tracks WHERE embedding MATCH ? AND k = ?",
    [serialize_float32(query_embedding), 100]
).fetchall()
```

### Distance metrics

| Metric | How to specify | Notes |
|---|---|---|
| L2 (Euclidean) | `distance_metric=l2` (default) | For unnormalised vectors |
| Cosine | `distance_metric=cosine` | Best for EffNet embeddings (unit-normalised) |
| L1 (Manhattan) | `vec_distance_L1(a, b)` | Manual function only |
| Hamming | `vec_distance_hamming(a, b)` | Binary vectors only |

The metric is set per-column when creating the virtual table. For Crate's EffNet embeddings (which encode musical similarity as direction, not magnitude), **cosine** is appropriate.

### Essentia EffNet embedding dimension

From `backend/importer/essentia_analysis.py` line 288:
```python
raw = model(audio_16k)  # (batch, 1280)
```

The Discogs-EffNet backbone produces **1280-dimensional float32 embeddings**. This is also confirmed for the variant models (`embedding_track`, `embedding_artist`, `embedding_label`, `embedding_release`) — all use the same 1280-dim EffNet architecture.

The virtual table declaration for Crate must use `FLOAT[1280]`.

### Known limitations

- **Pre-v1**: Breaking changes possible; pin the version in `pyproject.toml`
- **Separate virtual table**: Cannot embed a vec column in the main `tracks` table — must JOIN
- **No explicit dimension limit documented**: The project page does not state a maximum dimension; 1280 is well within typical usage
- **No explicit row count limit documented**: At 20,000 tracks, performance should be well within range
- **Thread safety**: Not documented. Follow the same caution as Essentia — do not share connections across threads; each worker thread should have its own connection
- **SQLite ≥ 3.41 recommended**: WSL2 ships 3.45.1, so this is satisfied
- **macOS**: System Python on macOS bundles an SQLite that does not support extensions — requires Homebrew Python. Not a Crate concern (WSL2 is the runtime)

---

## Schema Structure Options

Three patterns for storing multi-source importer output. Evaluated against Crate's actual query patterns:

**Common Crate queries:**
- Filter by BPM range, key, label, year (SQL WHERE)
- Vector KNN search on EffNet embedding (Stage 2 of crate fill)
- Full-text or LIKE search on title/artist
- Sort by energy_score, darkness_score, etc.
- SELECT all resolved fields for Claude ranking (Stage 3)

### Option A — Single wide table

All importer outputs in one `tracks` table. Every row has ~100–150 columns, most NULL for any given track.

| Dimension | Assessment |
|---|---|
| Query complexity | Minimal — no JOINs. All filter/sort in one WHERE clause. |
| Write complexity | Single INSERT OR REPLACE per track. Simple. |
| Re-import one source | Must UPDATE specific columns. Low risk of overwriting unrelated data if column names are source-prefixed. |
| Schema evolution | `ALTER TABLE ADD COLUMN` for new fields — straightforward as long as new columns are nullable or have constant defaults. |
| NULL density | High. A track with no AcoustID match has ~20 NULL columns. Not a performance problem in SQLite. |
| Readability | Schema is large but self-documenting if column names are prefixed by source. |

Weakness: If a column is queried that spans all rows (e.g. `bpm`), the table is wide — but SQLite stores values column-by-column for B-tree pages and the query planner handles wide tables fine at 20,000 rows.

### Option B — One table per importer source

`tracks` (file identity + hash only) + `track_tags` + `track_acoustid` + `track_musicbrainz` + `track_discogs` + `track_itunes` + `track_essentia`. Joined on `track_id`.

| Dimension | Assessment |
|---|---|
| Query complexity | High. Every query involving fields from multiple sources requires JOINs across 3–7 tables. Crate fill Stage 3 (passing all fields to Claude) needs a 7-way JOIN. |
| Write complexity | Multiple INSERTs per track across multiple tables in a transaction. More code, more failure points. |
| Re-import one source | Clean: DELETE + INSERT for one table only. |
| Schema evolution | Add a new table for a new source. Clean in theory, but existing queries don't break. |
| NULL density | Per-source tables have no NULLs for present importers — but rows simply don't exist for absent importers, requiring LEFT JOINs everywhere. |
| Performance | More JOIN overhead. At 20,000 rows this is still fast, but queries are harder to write correctly and harder to index. |

Weakness for Crate: The three-stage crate fill funnel (SQL → vector → Claude) is the primary read pattern. Stage 1 SQL filters need BPM, key, label, year — which span `track_essentia`, `track_musicbrainz`, and `track_discogs`. That is a 3-table JOIN just for the filter step, every time.

### Option C — Hybrid (canonical resolved fields + raw per-source tables)

`tracks` holds: file identity, hash, resolved canonical fields (`resolved_title`, `resolved_artist`, `resolved_bpm`, `resolved_key`, `resolved_label`, `resolved_year`, `resolved_artwork_url`), and core Essentia floats used in filtering.

Raw importer outputs in per-source tables (`track_tags`, `track_acoustid`, etc.) for auditability and re-resolution.

| Dimension | Assessment |
|---|---|
| Query complexity | Low for Stage 1 filter (all resolved fields in `tracks`). JOIN to raw tables only needed for deep audit or re-processing. |
| Write complexity | Higher: must compute and write resolved fields as well as raw fields. Resolution logic must be centralised. |
| Re-import one source | Update the raw source table, then rerun resolution to update `tracks`. Two-step, but clean. |
| Schema evolution | Add columns to the raw table for a new source. Add new resolved fields to `tracks` if needed. |
| Derived scores | Fit naturally into `tracks` alongside resolved fields. |
| Auditability | Full raw output preserved — can always trace why a resolved value was chosen. |

### Recommendation: Option A

**Use a single wide `tracks` table.**

Reasoning:

1. **Crate fill Stage 1 is the hot path.** Filtering 20,000 tracks by BPM, key, label, year must be fast and index-friendly. A single table with column indexes is optimal — no JOINs.

2. **20,000 rows is not a large dataset.** The wide-table concern ("100+ columns is unwieldy") is a PostgreSQL-era concern. SQLite at 20,000 rows with 150 columns is trivially fast. A `SELECT *` on all columns takes microseconds.

3. **NULL columns are harmless.** SQLite stores NULLs efficiently. A column that is NULL for 70% of rows (e.g. `acoustid_id` when AcoustID doesn't match) does not waste space — SQLite only stores non-NULL values in the B-tree.

4. **Single INSERT OR REPLACE per track.** The import pipeline writes one row per track. Re-importing a single source means running one UPDATE statement targeting that source's columns. With source-prefixed column names (`mb_title`, `discogs_label`, `itunes_artwork_url`), there is no risk of accidentally overwriting another source's data.

5. **Schema evolution via ALTER TABLE ADD COLUMN.** New importers (Last.fm, Deezer) just add new nullable columns. No migration complexity.

6. **Resolution is simple.** The `resolved_*` fields (title, artist, BPM, key, label, year) live in the same table. The fallback chain logic writes directly to the same row.

Option B is rejected: the JOIN cost for Stage 1 SQL filters is paid on every crate fill, and the query code becomes significantly more complex for no meaningful benefit at this scale.

Option C is rejected as premature: the "raw vs resolved" split only pays off if you need to audit resolution decisions or re-resolve from raw data independently. At v1, the import pipeline can simply overwrite and re-resolve. If auditing becomes important in Phase 2+, raw source tables can be added then.

---

## JSON Columns

### The pattern

SQLite has no native array type. Arrays (e.g. Discogs styles, Essentia genre probabilities, instrument labels, mood/theme labels) are stored as **JSON TEXT columns**.

```sql
-- Declaration
discogs_styles TEXT,            -- e.g. '["Techno","Industrial"]'
genre_probabilities TEXT,       -- e.g. '[0.32, 0.01, 0.18, ...]'  (400 floats)
genre_top_labels TEXT,          -- e.g. '["Techno","House","Minimal"]'
```

### json_extract and json_each — exact syntax

Both functions available since **SQLite 3.9.0**. WSL2 ships 3.45.1. No version concern.

**json_extract — read a value by path:**
```sql
-- Get first element
SELECT json_extract(discogs_styles, '$[0]') FROM tracks;

-- Get a named key from an object
SELECT json_extract(essentia_data, '$.bpm') FROM tracks;
```

**json_each — expand an array into rows:**
```sql
-- Find all tracks with 'Techno' in discogs_styles
SELECT DISTINCT t.id, t.resolved_title
FROM tracks t, json_each(t.discogs_styles) AS style
WHERE style.value = 'Techno';
```

`json_each` returns columns: `key` (array index), `value`, `type`, `atom`, `id`, `parent`, `fullkey`, `path`.

**Performance characteristic:** `json_each` on every row is a full table scan + JSON parse per row. For a 20,000-track library this is fast enough for one-off queries (tens of milliseconds). It is **not** suitable as the primary filter in Stage 1 of crate fill — use denormalised indexed columns for that.

### Denormalisation strategy

For fields that are frequently filtered (e.g. genre/style tags used in crate fill Stage 1), store both:

1. **Raw JSON column** — full array, for display, Claude ranking, and re-processing
2. **Denormalised TEXT column** — space-separated or comma-separated string for LIKE/GLOB queries, with a standard index

```sql
discogs_styles          TEXT,   -- JSON: '["Techno","Industrial"]'
discogs_styles_search   TEXT,   -- flat: 'Techno Industrial' — indexed, used in WHERE LIKE
```

The denormalised column is written by the import pipeline at the same time as the JSON column. A LIKE query on an indexed TEXT column is faster than `json_each` at scale, though at 20,000 rows either is fast.

**Probability arrays** (genre_probabilities: 400 floats, instrument_probabilities: 40 floats, moodtheme_probabilities: 56 floats) are stored as JSON TEXT only — they are never directly filtered in SQL. Filtering uses the `_top_labels` companion fields.

### Junction tables — when to use them

A junction table (e.g. `track_styles(track_id, style)`) is better than a JSON column when:

- You need exact-match queries like `WHERE style = 'Dub Techno'` run frequently
- You need aggregations like `COUNT(DISTINCT track_id) GROUP BY style`
- The set of values is large and unbounded (e.g. MusicBrainz tags — thousands of distinct values)

For Crate v1, the denormalised TEXT column approach (LIKE `'%Techno%'`) is sufficient. Junction tables are over-engineering at 20,000 tracks unless style-based browsing becomes a primary feature. Revisit in Phase 3 when the `/tracks` filter API is built.

### Essentia probability arrays

The following Essentia fields are large arrays that must be stored as JSON TEXT:

| Field | Type | Size |
|---|---|---|
| `genre_probabilities` | float array | 400 values (Discogs EffNet classes) |
| `genre_top_labels` | string array | top N labels (configurable, default 5) |
| `instrument_probabilities` | float array | 40 values (MTG-Jamendo) |
| `instrument_top_labels` | string array | top N |
| `moodtheme_probabilities` | float array | 56 values (MTG-Jamendo) |
| `moodtheme_top_labels` | string array | top N |
| `mfcc_mean` | float array | 13 values |
| `mfcc_var` | float array | 13 values |
| `bark_bands_mean` | float array | 27 values |
| `beat_ticks` | float array | variable (one per beat) |
| `bpm_estimates` | float array | variable |
| `bpm_intervals` | float array | variable |
| `danceability_dfa` | float array | variable |
| `pitch_frames` | float array | variable (per-frame, very large) |
| `pitch_confidence_frames` | float array | variable |
| `onset_times` | float array | variable |

Variable-length arrays (beat_ticks, pitch_frames, etc.) should be stored as JSON TEXT. They are not queried in SQL; they are read back for derived score computation or display only.

The main EffNet `embedding` (1280 floats) is stored separately in the `vec_tracks` virtual table, not as a JSON column. See the sqlite-vec section above.

---

## Schema Migration Pattern

### PRAGMA user_version

```sql
-- Read the current version
PRAGMA user_version;

-- Set the version (integer, application-defined)
PRAGMA user_version = 3;
```

`user_version` is a 32-bit signed integer stored at byte offset 60 in the SQLite database file header. SQLite does not use it — it is entirely application-managed.

**In :memory: databases:** `user_version` does NOT persist across connections. Each new in-memory connection starts at version 0. In tests using `:memory:`, the migration runner will re-apply all migrations on every test — which is the desired behaviour (tests always start from a clean, up-to-date schema).

### ALTER TABLE limits

What SQLite `ALTER TABLE` supports (as of 3.45.1):

| Operation | Supported |
|---|---|
| `RENAME TABLE` | Yes |
| `RENAME COLUMN` | Yes |
| `ADD COLUMN` | Yes, with restrictions |
| `DROP COLUMN` | Yes (since 3.35.0) |
| Modify column type | **No** |
| Add/remove PRIMARY KEY | **No** |
| Add/remove UNIQUE constraint | **No** |
| Change column order | **No** |
| Add CHECK/FOREIGN KEY/NOT NULL | **No** |

**Restrictions on ADD COLUMN:**

- Cannot add a column with `PRIMARY KEY` or `UNIQUE`
- Cannot use `CURRENT_TIME`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, or any parenthesised expression as the DEFAULT value
- `NOT NULL` requires a non-NULL constant DEFAULT value
- Cannot add a `STORED` generated column (only `VIRTUAL` generated columns)

```sql
-- Valid
ALTER TABLE tracks ADD COLUMN deezer_bpm REAL;
ALTER TABLE tracks ADD COLUMN last_fm_listeners INTEGER;
ALTER TABLE tracks ADD COLUMN new_flag INTEGER NOT NULL DEFAULT 0;

-- Invalid — CURRENT_TIMESTAMP default
ALTER TABLE tracks ADD COLUMN imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
-- Workaround: add without default, populate separately; or use table rebuild
```

For unsupported changes (type modifications, constraint changes), the full 12-step procedure is required: create new table with desired schema, copy data, drop old table, rename new table.

### Migration runner design (Python)

```python
# Pattern — do not implement here; this is Phase 2 work

MIGRATIONS = [
    (1, "sql for migration 1"),
    (2, "sql for migration 2"),
    (3, "sql for migration 3"),
]

def run_migrations(conn):
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in MIGRATIONS:
        if version > current:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
```

Key points:
- Read `user_version` once at startup
- Apply only migrations with version > current version
- Update `user_version` immediately after each migration (inside the same transaction if possible, but `PRAGMA user_version = N` cannot be used inside an explicit `BEGIN` transaction with `executescript` — set it after each script commits)
- Migrations are applied in order, never skipped

### WAL mode and foreign keys

`PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` (already set in Crate's `get_db()`) do not interfere with migrations, with one note:

- **WAL mode** is safe during schema changes. `ALTER TABLE` and `CREATE TABLE` acquire an exclusive lock and complete atomically.
- **Foreign keys** interact with `ALTER TABLE DROP COLUMN`: if a column is referenced by a foreign key constraint (in the same or another table), the drop will fail. When dropping columns in migrations, temporarily disable foreign keys: `PRAGMA foreign_keys=OFF`, perform the operation, re-enable.

---

## Indexes

### How SQLite B-tree indexes work

SQLite implements indexes as separate B-tree tables containing the indexed column values plus the rowid, sorted by the indexed values. A query on an indexed column does a binary search on the index B-tree to find matching rowids, then looks up those rowids in the main table. A **covering index** (index containing all columns needed by the query) eliminates the second lookup entirely.

### UNIQUE constraint vs UNIQUE index

In SQLite, `UNIQUE` constraints and `CREATE UNIQUE INDEX` are functionally equivalent — both create the same underlying B-tree structure. `UNIQUE` constraint in `CREATE TABLE` creates an implicit unique index. You cannot have one without the other. Use whichever is clearer for the intent.

### EXPLAIN QUERY PLAN

```sql
EXPLAIN QUERY PLAN
SELECT id, resolved_title FROM tracks
WHERE resolved_bpm BETWEEN 128 AND 135;
```

Output will show either:
- `SEARCH tracks USING INDEX idx_tracks_bpm (resolved_bpm>? AND resolved_bpm<?)` — index is used
- `SCAN tracks` — full table scan (no usable index)

Run this for any query used in Stage 1 of crate fill to verify indexes are active.

### Which columns to index for Crate

**High priority — used in Stage 1 SQL filter (every crate fill):**

| Column | Index type | Reason |
|---|---|---|
| `resolved_bpm` | Standard | BPM range queries: `BETWEEN 128 AND 135` |
| `resolved_key` | Standard | Exact match or harmonic key set: `IN ('Am', 'Dm', ...)` |
| `resolved_label` | Standard | Exact match: `= 'Tresor'` |
| `resolved_year` | Standard | Year range: `BETWEEN 2010 AND 2020` |
| `file_path` | UNIQUE | Import deduplication; also primary lookup |
| `file_hash` | Standard | Hash-based change detection on re-import |

**Medium priority — used in library browse API (/tracks filter):**

| Column | Index type | Reason |
|---|---|---|
| `resolved_artist` | Standard | Filter/sort by artist |
| `resolved_title` | Standard | Text search (used with LIKE) |
| `acoustid_id` | Standard | Used in partial index below |

**Partial indexes — useful for Crate:**

```sql
-- Index only tracks where AcoustID matched (acoustid_id IS NOT NULL)
-- Reduces index size; crate fill Stage 1 often filters to matched tracks only
CREATE INDEX idx_acoustid_matched ON tracks(acoustid_id)
WHERE acoustid_id IS NOT NULL;

-- Index only tracks where Essentia has run
CREATE INDEX idx_essentia_ready ON tracks(bpm, integrated_loudness)
WHERE bpm IS NOT NULL;
```

Partial indexes are supported since SQLite 3.8.0. WHERE clause can reference any column in the table, not just the indexed columns. The query planner uses a partial index when the query's WHERE clause logically implies the index's WHERE clause.

### Covering indexes

At 20,000 tracks, covering indexes are unlikely to provide meaningful benefit over standard indexes — the main table is small enough that the second B-tree lookup adds negligible time. Design for correctness and simplicity; add covering indexes only if `EXPLAIN QUERY PLAN` shows a bottleneck.

### Index prefix rule

Do not create an index that is a prefix of another. If you have:

```sql
CREATE INDEX idx_bpm_key ON tracks(resolved_bpm, resolved_key);
```

You do not also need `CREATE INDEX idx_bpm ON tracks(resolved_bpm)` — the multi-column index serves both purposes.

---

## BLOB Fallback for Embeddings

If sqlite-vec is unavailable at runtime (extension cannot be loaded), embeddings can be stored as BLOB in the main `tracks` table.

### Serialisation — numpy float32 to BLOB

```python
import numpy as np

embedding = np.array([...], dtype=np.float32)   # shape (1280,)
blob = embedding.tobytes()                        # 1280 * 4 = 5120 bytes
```

### Deserialisation — BLOB to numpy float32

```python
import numpy as np

blob = row["embedding_blob"]                      # bytes from sqlite3 cursor
embedding = np.frombuffer(blob, dtype=np.float32) # shape (1280,)
```

Both operations complete in under 1 ms. They are the canonical pattern for storing numpy arrays in SQLite.

### Storage size

- 1280 float32 values × 4 bytes = **5,120 bytes per track**
- 20,000 tracks × 5,120 bytes = **~100 MB** total for embeddings only

This is well within SQLite's practical limits. The `tracks` table with BLOB embeddings would be roughly 100–150 MB — entirely feasible.

### Brute-force cosine similarity (Python fallback)

Without sqlite-vec, similarity search requires reading all embeddings and computing in Python:

```python
import numpy as np
import sqlite3

def find_similar(conn, query_embedding: np.ndarray, k: int = 100) -> list:
    rows = conn.execute(
        "SELECT id, embedding_blob FROM tracks WHERE embedding_blob IS NOT NULL"
    ).fetchall()

    query = query_embedding / np.linalg.norm(query_embedding)
    scores = []
    for track_id, blob in rows:
        emb = np.frombuffer(blob, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)
        score = float(np.dot(query, emb))
        scores.append((track_id, score))

    scores.sort(key=lambda x: -x[1])
    return scores[:k]
```

**Performance estimate at 20,000 tracks (1280-dim float32):**

- Reading all BLOBs from disk: ~10–50 ms (depends on disk speed; 100 MB read)
- NumPy cosine similarity for 20,000 × 1280: ~200–500 ms on a typical CPU (can be vectorised with `np.dot(embeddings_matrix, query)` for a 10–50× speedup)
- With vectorised matrix multiply (load all into a numpy matrix once at startup): **~5–20 ms** for the similarity step alone

Vectorised approach:
```python
# Pre-load on startup
embeddings_matrix = np.zeros((len(track_ids), 1280), dtype=np.float32)
# ... load from DB and normalise rows ...

# Query
scores = embeddings_matrix @ query_normalised  # shape (N,)
top_k = np.argsort(scores)[-k:][::-1]
```

**Conclusion:** The BLOB fallback is feasible at 20,000 tracks if embeddings are pre-loaded into a NumPy matrix at startup. With a per-query loop (reading BLOBs on demand), it is slower but still usable for a local app. JSON TEXT (list of floats) is significantly slower than BLOB: JSON parsing adds 5–10× overhead — do not use JSON TEXT for embeddings.

---

## Open Questions

1. **sqlite-vec thread safety** — Not documented. The recommendation is to use one connection per thread. Whether concurrent reads on separate connections to the same vec0 virtual table are safe is not confirmed. For Crate's import pipeline (max 2 worker threads), the conservative approach is to perform all vec0 writes on the main thread sequentially.

2. **sqlite-vec version pinning** — The project is pre-v1. The exact version that will be stable enough for Phase 2 is unknown. Pin the version in `pyproject.toml` and review on upgrade.

3. **embedding_track / embedding_artist / embedding_label / embedding_release storage** — `essentia_analysis.py` produces four additional 1280-dim embeddings per track (variant EffNet models). Whether all four are stored in sqlite-vec (four separate vec0 virtual tables) or only the primary `embedding` is stored needs a decision in Phase 2. Storage cost: 4 × 5,120 bytes × 20,000 tracks = ~400 MB additional. This may be best deferred to Phase 2 after validating that the primary embedding alone is sufficient for crate fill quality.

4. **Discogs, Last.fm, Deezer field mapping** — These three sources have not been fully researched yet. Their output fields will add additional columns to the `tracks` table. The schema design in Phase 2 must wait until these are confirmed. See CLAUDE.md Phase 1 remaining tasks.

5. **PRAGMA user_version inside WAL transactions** — The exact interaction between `PRAGMA user_version = N` and WAL mode has not been tested. The pragma writes to the database header, which requires acquiring a write lock. In practice this is straightforward, but the migration runner should set `user_version` outside of a `BEGIN...COMMIT` block to avoid any locking interactions.
