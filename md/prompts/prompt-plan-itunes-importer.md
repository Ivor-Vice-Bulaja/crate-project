# Task: Plan the iTunes Search API Importer Module

## Context

Read CLAUDE.md before starting. This is a planning task — no code is written here.
The output is a detailed implementation plan that will be used to build
`backend/importer/itunes.py` in Phase 2.

The research for this plan is complete. All iTunes Search API endpoint structures, exact
field names, presence guarantees, and exception types are documented in
`docs/research/itunes.md`. Read that document in full before producing any plan —
do not rely on prior knowledge about the iTunes Search API.

**Core principle:** This module looks up a track on the iTunes Search API and returns a flat
dictionary of raw API fields. It does not score, rank, or derive anything — it stores what
iTunes gives us and lets later stages decide what to do with it. The goal is to lose as
little information as possible from the response.

**Role in the pipeline:** iTunes is optional enrichment only. Its primary value is artwork
URLs and day-precision release dates. It does not provide label, catalogue number, or ISRC.
Do not treat it as a primary source for any field that MusicBrainz or Discogs already covers.

---

## What to plan

Design the implementation of `backend/importer/itunes.py` — the module that takes track
metadata (artist, title, duration) and returns a flat dictionary of raw iTunes fields
ready to be written to the SQLite database.

### 1. Module interface

Define the exact function signature and return type. The function will be called from
`backend/importer/pipeline.py` in a ThreadPoolExecutor.

- What does the function take as input? (which metadata fields, any config?)
- What does it return on success? (flat dict of raw fields)
- What does it return on no match (zero search results after all strategies)?
- What does it return on low-confidence match (multiple candidates, no clear winner)?
- What does it return on total failure (network error, unhandled exception)?
- Should errors be raised or returned as structured data?

The module uses raw `requests` HTTP calls — no iTunes-specific Python library exists
(confirmed in research doc). Note this in the interface section.

### 2. Search strategy

The iTunes Search API supports only one search mechanism: keyword search via `term`.
There is no catno or barcode equivalent. The research doc establishes that searching
`term=artist+title` with `media=music&entity=song` is the correct approach.

Specify the complete decision tree:

- **Primary strategy:** `term="{artist} {title}"`, `media=music`, `entity=song`,
  `country=us`, `limit=5`. When to use this.
- **Country fallback:** If the US storefront returns zero results, the research doc
  notes that `country=gb` and `country=de` may find releases absent from `country=us`
  (e.g., some Kompakt/German releases). Specify whether to attempt country fallbacks,
  how many storefronts to try, and what order (us → gb → de).
- **Zero results on primary strategy:** define which fallback strategies to attempt.
  The research doc notes that a `term` query for a common title returns noise — always
  use both artist and title together; never search title alone.
- **When to stop:** define the termination condition (no match after N strategies).

Note: there is no catno or barcode search path. The only lookup that bypasses `term`
is `?id=<trackId>` — specify whether to use this for re-lookups (when a `trackId` is
already stored) vs. fresh imports.

### 3. Candidate selection

When a search returns multiple results, specify the scoring logic for selecting the
best match. The research doc identifies these signals:

| Signal | Use |
|---|---|
| `artistName` fuzzy match against known artist | High confidence |
| `trackName` fuzzy match against known title | High confidence |
| Duration match (`trackTimeMillis` vs file duration ±30s) | High confidence — reject outside threshold |
| `primaryGenreName` match | Weak signal — too coarse to use |
| `collectionName` match against known album | Medium signal |
| `releaseDate` year proximity to known year | Weak signal |

The research doc warns that:
- Duration is the best version-disambiguation signal (radio edit vs 12" original)
- `primaryGenreName` is unreliable for techno/house — do not use it in scoring

Specify:
- How to compute a confidence score from these signals
- What threshold constitutes "clear winner" vs. "low confidence"
- What the duration rejection threshold is (research doc suggests ±30s; note this
  should be configurable)
- What to return when confidence is low (store top candidate with a confidence flag,
  or skip and return no match)
- How to handle a single result (is it automatically accepted, or still scored?)

### 4. API call sequence

For a matched track, specify every API call made and every field extracted from
the response.

**Primary call — search:**
```
GET https://itunes.apple.com/search
    ?term={artist}+{title}&media=music&entity=song&country=us&limit=5
```

**Optional call — lookup by ID:**
```
GET https://itunes.apple.com/lookup?id={trackId}
```
Specify when this is used (re-lookup of a previously stored `trackId` vs. initial
import). State whether this replaces the search call entirely for re-lookups, or
supplements it.

From the search/lookup response, list every field to extract and store, using the
exact JSON key names from the research doc. Do not omit fields on the grounds that
they "might not be useful" — store everything except fields explicitly noted as junk
(`currency`, `collectionPrice`, `trackPrice`, `trackCensoredName`,
`collectionCensoredName`).

For `artworkUrl100`: the research doc documents URL templating to retrieve larger
artwork. Specify whether to store the raw `artworkUrl100` value as-is, or to
transform it to a larger size (e.g., `600x600bb.jpg`) before storing. Note the
risk: this templating is not officially documented. State the decision and why.

State the total API call budget per track (minimum and maximum).

### 5. Output schema

Define the complete return dictionary. For every key:
- Key name (snake_case, prefixed `itunes_`)
- Source endpoint and exact JSON key
- Python type after extraction
- Nullable? (and when)

The plan must include at minimum these fields:

```
# Match metadata
itunes_track_id         int         trackId                         None on no match
itunes_artist_id        int         artistId                        None on no match
itunes_collection_id    int         collectionId                    None on no match
itunes_confidence       str         "high"/"low"/"none"             always set

# Track identity
itunes_track_name       str         trackName                       None on no match
itunes_artist_name      str         artistName                      None on no match
itunes_collection_name  str         collectionName                  None on no match
itunes_release_date     str         releaseDate (ISO 8601 string)   None if absent
itunes_track_time_ms    int         trackTimeMillis                 None if absent

# Track position
itunes_disc_count       int         discCount                       None if absent
itunes_disc_number      int         discNumber                      None if absent
itunes_track_count      int         trackCount                      None if absent
itunes_track_number     int         trackNumber                     None if absent

# Genre
itunes_genre            str         primaryGenreName                None if absent

# Explicit / streaming
itunes_track_explicit   str         trackExplicitness               None if absent
itunes_is_streamable    bool        isStreamable                    None if absent

# Artwork
itunes_artwork_url      str         artworkUrl100 (possibly templated to larger size)
                                                                    None if absent

# View URLs
itunes_track_url        str         trackViewUrl                    None if absent
itunes_artist_url       str         artistViewUrl                   None if absent
itunes_collection_url   str         collectionViewUrl               None if absent

# Compilation fields (present on Various Artists only)
itunes_collection_artist_id     int     collectionArtistId          None if absent
itunes_collection_artist_name   str     collectionArtistName        None if absent

# Lookup metadata
itunes_search_strategy  str         "artist_title"/"id"/"none"      always set
itunes_country          str         country parameter used          always set
itunes_lookup_timestamp str         ISO 8601                        always set
```

Do NOT store `previewUrl` — the research doc confirms these are transient/expiring
CDN URLs and must not be cached. State this explicitly in the schema section.

Do NOT store price fields (`collectionPrice`, `trackPrice`, `currency`) — not relevant.

### 6. Error handling

- **Zero search results (no match):** return dict with all fields as None,
  `itunes_confidence = "none"`, `itunes_search_strategy = "none"`. Do not raise.
- **Low-confidence match:** return dict with data extracted but
  `itunes_confidence = "low"` to flag for manual review.
- **HTTP 403 (rate limit):** the research doc states 403 is the rate-limit response
  (not 429). Log at WARNING. Back off 60 seconds and retry once. If still 403,
  return error dict with `itunes_error` field set.
- **HTTP 429:** treat identically to 403 (research doc notes 429 is possible though
  undocumented). Same backoff and retry logic.
- **HTTP 400 (malformed request):** log at ERROR with the full request URL (a 400
  indicates a code bug). Do not retry. Return error dict.
- **HTTP 5xx (Apple service error):** log at WARNING. Retry with exponential backoff
  (1s, 2s, 4s). Skip after 3 failures. Return error dict.
- **Network timeout:** log at WARNING, return error dict.
- **Top-level fallback:** the entire function should be wrapped to never raise —
  always return a dict (possibly all-None with an `itunes_error` field).

Define what the error dict looks like (which fields are set, which are None).

### 7. Rate limiting strategy

At ~20 req/min (soft limit, per IP, mechanism unconfirmed — see open questions):
- At full concurrency with 2 workers, worst-case rate is ~40 req/min — potentially
  over the limit
- Per-track call budget is 1–2 calls (search + optional re-lookup)
- For a 10,000-track library with 40% match rate: ~4,000 successful searches +
  ~6,000 no-match searches = ~10,000 total calls ≈ 8 hours at 20 req/min

Specify:
- Whether to use a fixed inter-request delay (research doc suggests 3.1s = ~19/min)
  or adaptive throttling based on 403 responses
- Whether the delay applies per-worker or is shared across workers
  (at 2 workers, 3.1s per worker = 6.2s between any two calls — effectively
  ~10 req/min, well under the limit)
- What happens when a 403 is received mid-batch
- Whether a `requests.Session` is shared across calls (note thread safety: a
  `Session` is not thread-safe without a lock; specify either one session per
  thread or a lock around session use)
- No third-party rate-limit library is needed — the research doc confirms raw
  `requests` is appropriate

### 8. Configuration

Identify every value that should not be hardcoded. For each:
- What it controls
- Where it lives (function argument, config dataclass, `backend/config.py`)
- Its default value

At minimum:
- `user_agent` — User-Agent string sent with all requests (Apple may block generic user agents)
- `max_search_results` — how many results to score when selecting a candidate (default 5)
- `confidence_threshold` — minimum score to accept a match as "high" confidence
- `duration_tolerance_seconds` — maximum duration difference to accept a match (default 30)
- `country_fallbacks` — list of country codes to try after US fails (default `["gb", "de"]`)
- `fetch_lookup` — boolean: whether to use the `?id=` endpoint for re-lookups
- `artwork_size` — pixel size for artwork URL templating (default `600`; note undocumented behaviour)
- `rate_limit_delay` — inter-request delay in seconds (default `3.1`)

### 9. Test plan

Describe the tests for `backend/tests/test_importer/test_itunes.py`:

- **No live API calls in tests.** All HTTP is mocked. Use `unittest.mock` or
  `pytest-mock` to patch `requests.get`. No real network requests.
- **Fixture structure:** define a minimal mock track result dict with all fields
  used by the module. Mirrors the real iTunes JSON response object.
- **Happy path tests:**
  - artist+title search returns one result → correct fields extracted
  - Multiple results → highest-scoring candidate selected (duration closest to file)
  - Duration within ±30s → accepted; duration outside threshold → rejected
  - `previewUrl` present in response → NOT stored in output dict
  - `artworkUrl100` → transformed to `600x600bb.jpg` size (if templating enabled)
- **Country fallback tests:**
  - US storefront returns zero → falls back to `country=gb` → succeeds
  - All country storefronts return zero → returns no-match dict with
    `itunes_confidence = "none"`
- **Failure path tests:**
  - HTTP 403 → backs off 60s, retries once, succeeds → high confidence result
  - HTTP 403 → backs off, retries, still 403 → error dict returned, no exception
  - HTTP 5xx → retries with backoff → error dict after 3 failures
  - `requests.exceptions.Timeout` → error dict returned, no exception propagates
  - Unknown exception → top-level fallback catches it, error dict returned
- **Field extraction tests:**
  - `collectionArtistId` / `collectionArtistName` present only on VA result → stored
  - `isStreamable` present → stored as bool
  - JSON-serialisable fields round-trip correctly

### 10. Open questions from the research doc

`docs/research/itunes.md` has 8 open questions. For each one that affects this
module, state whether it blocks the implementation plan or can be deferred, and
what the interim decision is.

Key questions to address:
- **Artwork URL templating upper bound:** the plan uses `600x600bb.jpg` substitution.
  This is community-reported, not officially documented. Does the plan store the raw
  `artworkUrl100` as a fallback, or commit to the templated URL? What is the interim
  decision?
- **`previewUrl` TTL:** confirmed as transient — do not store. This is already
  reflected in the schema. Confirm this is a non-blocking decision.
- **Rate limit enforcement mechanism (per-IP vs. per-account):** the plan uses
  a fixed 3.1s delay. Does uncertainty about the enforcement mechanism change this?
  Interim decision: treat it as per-IP, use the fixed delay, handle 403 as rate-limit
  signal.
- **`trackId` stability across re-ingests:** the plan proposes storing `itunes_track_id`
  for future re-lookups. If IDs can change, re-lookup adds little value. Interim
  decision: store the ID but do not rely on it as a permanent stable identifier.
- **Match rate on a real DJ library (30–50% estimate):** does the expected high
  no-match rate affect any design decisions? In particular, does it affect whether
  the country fallback is worth the extra API calls?
- **`version=1` vs `version=2`:** the plan uses `version=2` (default). This is a
  non-blocking deferral — confirm.
- **ISRC via authenticated Apple Music API:** out of scope for Phase 2. Confirm
  this is deferred.
- **Regional coverage difference for `country=de`:** the country fallback assumes
  `de` adds coverage for German labels (Kompakt, Tresor). This is not confirmed —
  interim decision: include `de` as a fallback but do not assume it will improve
  match rate significantly.

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/itunes-importer.md
```

Structure:

```
# Implementation Plan: iTunes Search API Importer Module

## Overview
One paragraph: what the module does, what it does not do, its role in the pipeline.

## Function Interface
Exact signature, return type, error contract. Note: raw requests, no iTunes library.

## Search Strategy
Decision tree: artist+title → country fallback → no match. API calls per strategy.

## Candidate Selection
Scoring logic, duration threshold, confidence threshold, low-confidence handling.

## API Call Sequence
Which calls are made, which fields are extracted from each response.

## Output Schema
Full table: key | source JSON key | type | nullable

## Error Handling
Specific strategy for each failure mode (403 backoff, 5xx retry, timeout).

## Rate Limiting
Per-worker delay, shared-session strategy, 403 handling mid-batch.

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

- [ ] `md/plans/itunes-importer.md` exists
- [ ] Search strategy covers the artist+title path and country fallback order with
      explicit termination condition
- [ ] Candidate selection specifies duration threshold and a concrete scoring approach
- [ ] API call sequence lists every field extracted with exact JSON key names
- [ ] Output schema table covers every field listed in section 5
- [ ] `previewUrl` is explicitly excluded from the schema with reason stated
- [ ] No derived scores or computed fields anywhere in the plan — only raw API outputs
- [ ] Error handling is specific for each failure mode (no match, 403, 400, 5xx, timeout)
- [ ] Rate limiting addresses per-worker delay and session thread safety
- [ ] Test plan specifies mocked HTTP (no live API calls) and covers all failure paths
- [ ] All open questions that affect the plan have a stated interim decision
- [ ] Implementation order is a concrete numbered list
