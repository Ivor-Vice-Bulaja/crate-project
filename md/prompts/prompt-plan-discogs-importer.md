# Task: Plan the Discogs API Importer Module

## Context

Read CLAUDE.md before starting. This is a planning task — no code is written here.
The output is a detailed implementation plan that will be used to build
`backend/importer/discogs.py` in Phase 2.

The research for this plan is complete. All Discogs API endpoint structures, exact
field names, presence guarantees, and exception types are documented in
`docs/research/discogs.md`. Read that document in full before producing any plan —
do not rely on prior knowledge about the Discogs API.

**Core principle:** This module looks up a release on Discogs and returns a flat
dictionary of raw API fields. It does not score, rank, or derive anything — it
stores what Discogs gives us and lets later stages decide what to do with it. The
goal is to lose as little information as possible from each endpoint's response.

---

## What to plan

Design the implementation of `backend/importer/discogs.py` — the module that takes
track metadata (artist, title, catalogue number, barcode, year) and returns a flat
dictionary of raw Discogs fields ready to be written to the SQLite database.

### 1. Module interface

Define the exact function signature and return type. The function will be called from
`backend/importer/pipeline.py` in a ThreadPoolExecutor.

- What does the function take as input? (which metadata fields, discogs_client.Client
  instance, any config?)
- What does it return on success? (flat dict of raw fields)
- What does it return on no match (zero search results after all strategies)? 
- What does it return on low-confidence match (multiple candidates, no clear winner)?
- What does it return on total failure (network error, unhandled exception)?
- Should errors be raised or returned as structured data?

### 2. Search strategy

The research doc establishes a priority order: catno > barcode > artist+title.
Different input combinations require different search calls.

Specify the complete decision tree:

- **If catno is known:** what parameters to send; whether to include artist as a
  narrowing filter; when to fall through to the next strategy
- **If barcode is known:** what parameters to send; whether to fall through
- **If only artist+title known:** which search parameters (`artist` + `release_title`
  vs. combined `q`); what format/style filters to add to reduce noise for a
  techno/house library
- **Zero results on first strategy:** define which fallback strategies to attempt
  and in what order — be specific about how many additional API calls this costs
- **When to stop:** define the termination condition (no match after N strategies)

All search calls use `type=release`. Specify whether to add `format=Vinyl` as a
default filter for a DJ library, and what to do if a vinyl-filtered search returns
zero results.

### 3. Candidate selection

When a search returns multiple results, specify the scoring logic for selecting the
best match. The research doc identifies these signals:

| Signal | Use |
|---|---|
| Exact catno match | High confidence |
| Exact artist name match | High confidence |
| Year within expected range | Medium signal |
| Format match (Vinyl 12") | Medium signal for DJ library |
| Country match | Weak signal |
| `community.have` count | Tiebreaker only |
| `data_quality` | Prefer `"Correct"` or `"Complete and Correct"` |

Specify:
- How to compute a confidence score from these signals
- What threshold constitutes "clear winner" vs. "low confidence"
- What to return when confidence is low (store top candidate with a confidence flag,
  or skip and return no match)
- How to handle a single result (is it automatically accepted, or still scored?)

### 4. API call sequence

For a matched release, specify every API call made and every field extracted from
each response:

**Mandatory call — full release:**
```
GET /releases/{id}
```

From the full release response, list every field to extract and store, using the
exact JSON path from the research doc (e.g. `labels[0].name`, `genres`,
`data_quality`). Do not omit fields on the grounds that they "might not be useful"
— store everything that's not obviously junk (images, videos, contributor lists).

**Optional call — master release:**
Specify when to fetch the master (`master_id` present and non-zero). What additional
fields does the master provide beyond what the release already contains? Is a master
fetch worth an extra API call?

**Optional call — label:**
Specify when to fetch the label. The research doc notes that `labels[].name` and
`labels[].catno` are already in the release response. What does a full label fetch
add (parent label, sublabels, profile)? Is it worth an extra API call per import?

State the total API call budget per track (minimum and maximum).

### 5. Output schema

Define the complete return dictionary. For every key:
- Key name (snake_case)
- Source endpoint and exact JSON path
- Python type after extraction
- Nullable? (and when)

The plan must include at minimum these fields:

```
# Match metadata
discogs_release_id      int         release.id                  None on no match
discogs_master_id       int         release.master_id           None if absent
discogs_confidence      str         "high"/"low"/"none"         always set
discogs_url             str         release.uri                 None on no match

# Release identity
discogs_title           str         release.title               None on no match
discogs_year            int         release.year                None if absent
discogs_country         str         release.country             None if absent
discogs_released        str         release.released            None if absent
discogs_status          str         release.status              None on no match
discogs_data_quality    str         release.data_quality        None on no match

# Label / catalogue
discogs_label           str         labels[0].name              None if absent
discogs_catno           str         labels[0].catno             None if absent
discogs_label_id        int         labels[0].id                None if absent

# Artists
discogs_artists         list[str]   artists[].name              None on no match  ← JSON
discogs_artists_sort    str         release.artists_sort        None if absent

# Genre / style
discogs_genres          list[str]   release.genres              None if absent    ← JSON
discogs_styles          list[str]   release.styles              None if absent    ← JSON

# Format
discogs_format_names    list[str]   formats[].name              None if absent    ← JSON
discogs_format_descs    list[str]   all formats[].descriptions  None if absent    ← JSON (merged)

# Producers / remixers
discogs_producers       list[str]   extraartists filtered by role   None if absent  ← JSON
discogs_remixers        list[str]   extraartists filtered by role   None if absent  ← JSON

# Tracklist
discogs_tracklist       list[dict]  tracklist (position+title+duration)  None if absent  ← JSON

# Identifiers
discogs_barcodes        list[str]   identifiers filtered by type="Barcode"  None if absent  ← JSON

# Community signals
discogs_have            int         community.have              None on no match
discogs_want            int         community.want              None on no match
discogs_rating_avg      float       community.rating.average    None on no match
discogs_rating_count    int         community.rating.count      None on no match

# Master release (if fetched)
discogs_master_year     int         master.year                 None if not fetched
discogs_master_url      str         master.uri                  None if not fetched

# Lookup metadata
discogs_search_strategy str         "catno"/"barcode"/"artist_title"/"none"  always set
discogs_lookup_timestamp str        ISO 8601                    always set
```

For `discogs_producers` and `discogs_remixers`: specify exactly which `role` strings
from `extraartists` map to each field. The research doc lists observed role values
(`"Producer, Written-By"`, `"Mixed By"`, `"Remix"`, etc.) — use them.

For `discogs_tracklist`: specify which sub-fields to include in each dict
(`position`, `title`, `duration`). Omit `type_`, `artists`, `extraartists` from the
stored dict unless there is a specific reason to include them.

For `discogs_format_descs`: the `formats` array has one object per physical item.
Specify whether to merge all `descriptions` arrays into a single flat list or to
preserve the per-format structure.

### 6. Error handling

- **Zero search results (no match):** return dict with all release fields as None,
  `discogs_confidence = "none"`, `discogs_search_strategy = "none"`. Do not raise.
- **Low-confidence match:** return dict with data extracted but
  `discogs_confidence = "low"` to flag for manual review.
- **HTTP 404:** treat as no match. Log at DEBUG level (not WARNING — expected for
  obscure releases).
- **HTTP 429 (rate limit):** python3-discogs-client retries automatically. If
  `TooManyAttemptsError` is raised after retries exhausted, log at WARNING and return
  error dict.
- **HTTP 5xx (Discogs outage):** log at WARNING, return error dict with
  `discogs_error` field set.
- **Network timeout:** log at WARNING, return error dict.
- **`discogs_client.exceptions.HTTPError`:** catch, log, return error dict. Do not
  re-raise.
- **Top-level fallback:** the entire function should be wrapped to never raise —
  always return a dict (possibly all-None with a `discogs_error` field).

Define what the error dict looks like (which fields are set, which are None).

### 7. Rate limiting strategy

At 60 req/min (authenticated) and 3 calls per track on average:
- At full concurrency with 2 workers, peak rate is ~6 calls/s — well under the limit
- However, the pipeline processes 5,000–20,000 tracks total, so total call count is
  significant (15,000–60,000 requests)

Specify:
- Whether to rely solely on python3-discogs-client's built-in backoff or add
  additional throttling
- Whether to check `X-Discogs-Ratelimit-Remaining` before each call
- What to do when the built-in backoff raises `TooManyAttemptsError`
- Whether the Client instance is shared across threads or created per-call
  (note: thread safety of python3-discogs-client is not confirmed in the research
  doc — address this)

### 8. Configuration

Identify every value that should not be hardcoded. For each:
- What it controls
- Where it lives (function argument, config dataclass, `backend/config.py`)
- Its default value

At minimum:
- `discogs_token` — personal access token (from env, never hardcoded)
- `user_agent` — User-Agent string sent with all requests
- `max_search_results` — how many search results to score when selecting a candidate
- `confidence_threshold` — minimum score to accept a match as "high" confidence
- `fetch_master` — boolean: whether to make the optional master fetch
- `fetch_label` — boolean: whether to make the optional label fetch
- `genre_top_n` — if storing only top N styles (or store all — make a decision)

### 9. Test plan

Describe the tests for `backend/tests/test_importer/test_discogs.py`:

- **No live API calls in tests.** All HTTP is mocked. Use `unittest.mock` or
  `pytest-mock` to patch `discogs_client.Client`. No real network requests.
- **Fixture structure:** define a minimal mock release object with all fields used
  by the module. A mock with `spec=discogs_client.Release` is ideal.
- **Happy path tests:**
  - catno search returns one result → correct fields extracted
  - barcode search returns one result → correct fields extracted
  - artist+title search returns one result → correct fields extracted
  - Multiple results → highest-scoring candidate selected
  - Master fetch enabled → `discogs_master_year` populated
- **Fallback tests:**
  - catno search returns zero → falls back to barcode → succeeds
  - All strategies return zero → returns no-match dict with `discogs_confidence = "none"`
- **Failure path tests:**
  - `HTTPError` raised → error dict returned, no exception propagates
  - `TooManyAttemptsError` raised → error dict returned
  - Unknown exception → top-level fallback catches it, error dict returned
- **Field extraction tests:**
  - `discogs_producers` contains only extraartists with role matching producer patterns
  - `discogs_remixers` contains only extraartists with role matching remix patterns
  - `discogs_format_descs` is a flat merged list when multiple formats present
  - JSON-serialisable fields (lists of strings/dicts) round-trip correctly

### 10. Open questions from the research doc

`docs/research/discogs.md` has 9 open questions. For each one that affects this
module, state whether it blocks the implementation plan or can be deferred, and
what the interim decision is.

Key questions to address:
- **Search authentication requirement:** live testing showed unauthenticated search
  working, but official docs say authentication is required. Does the plan assume
  authenticated search always?
- **Thread safety of python3-discogs-client:** is one Client instance safe to share
  across 2 threads, or does each thread need its own instance?
- **`master_id` presence in full release endpoint:** research doc notes that
  `master_id` may be absent (not 0) in the full release response when no master
  exists. How does the module detect this safely?
- **Match rate estimate (50–75%):** does the expected no-match rate affect any
  design decisions (e.g. how aggressively to fall back)?
- **Image 403 errors:** not storing images in Phase 2, so this is deferred. Confirm.

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/discogs-importer.md
```

Structure:

```
# Implementation Plan: Discogs API Importer Module

## Overview
One paragraph: what the module does, what it does not do.

## Function Interface
Exact signature, return type, error contract.

## Search Strategy
Decision tree: catno → barcode → artist+title → no match. API calls per strategy.

## Candidate Selection
Scoring logic, confidence threshold, low-confidence handling.

## API Call Sequence
Which calls are made, which fields are extracted from each response.

## Output Schema
Full table: key | source path | type | nullable

## Error Handling
Specific strategy for each failure mode.

## Rate Limiting
Client instance strategy, built-in backoff reliance, additional throttling (if any).

## Configuration
Table: parameter | controls | location | default

## Test Plan
Fixtures, mock strategy, happy path, fallback, failure, field extraction.

## Open Questions
Each relevant research question, plus interim decision.

## Implementation Order
Numbered steps to build this module in Phase 2.
```

---

## Definition of done

- [ ] `md/plans/discogs-importer.md` exists
- [ ] Search strategy covers all three input combinations (catno, barcode, artist+title)
      and defines fallback order and termination condition
- [ ] Candidate selection specifies a concrete scoring approach and confidence threshold
- [ ] API call sequence lists every field extracted from every endpoint with exact JSON paths
- [ ] Output schema table covers every field listed in section 5
- [ ] No derived scores or computed fields anywhere in the plan — only raw API outputs
- [ ] Error handling is specific for each failure mode (no match, 404, 429, 5xx, timeout)
- [ ] Rate limiting addresses thread safety and total call budget
- [ ] Test plan specifies mocked HTTP (no live API calls) and covers all failure paths
- [ ] All open questions that affect the plan have a stated interim decision
- [ ] Implementation order is a concrete numbered list
