# Implementation Plan: iTunes Search API Importer Module

## Overview

`backend/importer/itunes.py` takes a track's known metadata (artist, title, duration)
and returns a flat dictionary of raw iTunes Search API fields ready to be written to
SQLite. The module makes one or two HTTP calls using raw `requests` (no iTunes-specific
library exists), selects the best candidate from search results by scoring artist name,
track name, and duration similarity, and maps the chosen result to a fixed set of
`itunes_`-prefixed keys. It does not score, rank, or derive any application-level
values — it stores what iTunes returns and lets downstream stages decide what to do
with it. iTunes is optional enrichment; its primary value is artwork URLs and
day-precision release dates. It does not provide label, catalogue number, ISRC, BPM,
or key — do not treat it as a primary source for any field that MusicBrainz or Discogs
already covers.

---

## Function Interface

```python
def fetch_itunes(
    artist: str,
    title: str,
    duration_seconds: float | None,
    config: ItunesConfig,
) -> dict[str, object]:
```

**Inputs:**
- `artist` — known artist name (from MusicBrainz or file tags); used as the primary
  search term component
- `title` — known track title; used as the primary search term component
- `duration_seconds` — file duration from mutagen (float, seconds); used for candidate
  scoring and rejection; pass `None` if not available (disables duration scoring)
- `config` — `ItunesConfig` dataclass (see Configuration section); carries all tunable
  parameters so the caller can pass a single pre-built object

**Return on success (high or low confidence match):** flat `dict[str, object]` with all
`itunes_*` keys set to their extracted values (see Output Schema).

**Return on no match (zero results after all strategies):** same dict structure with all
data fields set to `None`, `itunes_confidence = "none"`,
`itunes_search_strategy = "none"`.

**Return on low-confidence match:** full data dict with `itunes_confidence = "low"`.
The best-scoring candidate is stored regardless — the confidence flag signals that the
match was not clear-cut and may need manual review.

**Return on total failure (network error, unhandled exception):** same dict structure
with all data fields set to `None`, `itunes_confidence = "none"`, and
`itunes_error` set to a short error description string.

**Errors are never raised.** The entire function is wrapped in a top-level
`try/except Exception` that catches anything not already handled and returns an error
dict. The caller in `pipeline.py` must not handle exceptions from this module — it
will always receive a dict.

**Note on HTTP library:** No iTunes-specific Python library exists. All HTTP calls use
raw `requests.get()`. No third-party rate-limiting library is needed.

---

## Search Strategy

The iTunes Search API supports only keyword search via the `term` parameter. There is
no label, catalogue number, or barcode search path. The only non-keyword lookup is
`?id=<trackId>` for when a `trackId` is already stored.

### Decision tree

```
1. If config.fetch_lookup is True AND a stored itunes_track_id is passed in:
       → Use the lookup-by-ID path (see API Call Sequence)
       → Skip all keyword search strategies
       → Return result (or error dict on failure)

2. PRIMARY STRATEGY: term="{artist} {title}", media=music, entity=song,
                     country=us, limit={config.max_search_results}
       → Score candidates (see Candidate Selection)
       → If a winner is found: return result
       → If zero results: proceed to COUNTRY FALLBACK

3. COUNTRY FALLBACK (only if US returns zero results):
       → Iterate through config.country_fallbacks in order: ["gb", "de"]
       → For each country:
             → Same search call, country parameter substituted
             → If results found: score candidates, return winner if found
             → If zero results: try next country
       → If all countries return zero results: proceed to NO MATCH

4. NO MATCH:
       → Return no-match dict (all None, confidence="none", strategy="none")
```

**Termination conditions:**
- A winner is found at any stage — stop immediately, do not try further countries
- All country storefronts (us + fallbacks) return zero results — return no-match dict
- The fallback list is exhausted without a winner — return no-match dict

**Never search title alone.** A bare title query produces high noise. Always use both
artist and title in the `term` parameter.

**Re-lookup path (step 1):** The `?id=` endpoint entirely replaces the keyword search
for a track where `itunes_track_id` is already stored. It is not used alongside search.
The caller in `pipeline.py` is responsible for passing the stored ID (or `None` for
fresh imports). For fresh imports this step is skipped entirely.

---

## Candidate Selection

### Scoring

When a search returns one or more results, score each candidate against the known
artist, title, and duration. Sum the sub-scores to produce a total confidence score.

| Signal | Sub-score | Notes |
|---|---|---|
| `artistName` fuzzy match vs known artist | 0.0–0.4 | Use `rapidfuzz.fuzz.token_sort_ratio` / 100 × 0.4 |
| `trackName` fuzzy match vs known title | 0.0–0.4 | Same method × 0.4 |
| Duration match (`trackTimeMillis` vs file duration) | 0.0–0.2 | Within ±30s: 0.2; outside: 0.0 (and reject — see below) |

Total possible score: 1.0.

**Duration rejection:** If `duration_seconds` is available AND the candidate's
`trackTimeMillis` differs by more than `config.duration_tolerance_seconds` (default
30s), the candidate is **rejected entirely** — it does not participate in selection
regardless of its fuzzy-match scores. This is the primary version-disambiguation
signal (radio edit vs 12" original).

If `duration_seconds` is `None`, the duration sub-score is omitted and not computed.
The maximum possible score becomes 0.8 in this case.

**Single result:** A single result is still scored. It is not automatically accepted.
If its score is below the threshold (or rejected by duration), return no-match.

**Confidence threshold:**
- Score ≥ `config.confidence_threshold` (default `0.7`): `itunes_confidence = "high"`
- Score > `0.0` but < threshold: `itunes_confidence = "low"` — store the top
  candidate with the low flag
- All candidates rejected or score = 0.0: return no-match dict

**Low-confidence handling:** Store the top-scoring candidate with
`itunes_confidence = "low"`. Do not discard the data — downstream stages can decide
whether to use it, and the flag enables future bulk review. Do not re-run the search
or attempt another strategy just because confidence is low.

---

## API Call Sequence

### Call 1 (always made on fresh import) — keyword search

```
GET https://itunes.apple.com/search
    ?term={artist}+{title}
    &media=music
    &entity=song
    &country={country}
    &limit={config.max_search_results}
```

Headers:
```
User-Agent: {config.user_agent}
```

Response fields to extract from the chosen result object:

| JSON key | Extracted as |
|---|---|
| `wrapperType` | (used for validation — must be `"track"`; not stored) |
| `kind` | (used for validation — must be `"song"`; not stored) |
| `trackId` | `itunes_track_id` |
| `artistId` | `itunes_artist_id` |
| `collectionId` | `itunes_collection_id` |
| `trackName` | `itunes_track_name` |
| `artistName` | `itunes_artist_name` |
| `collectionName` | `itunes_collection_name` |
| `releaseDate` | `itunes_release_date` |
| `trackTimeMillis` | `itunes_track_time_ms` |
| `discCount` | `itunes_disc_count` |
| `discNumber` | `itunes_disc_number` |
| `trackCount` | `itunes_track_count` |
| `trackNumber` | `itunes_track_number` |
| `primaryGenreName` | `itunes_genre` |
| `trackExplicitness` | `itunes_track_explicit` |
| `isStreamable` | `itunes_is_streamable` |
| `artworkUrl100` | `itunes_artwork_url` (transformed — see below) |
| `trackViewUrl` | `itunes_track_url` |
| `artistViewUrl` | `itunes_artist_url` |
| `collectionViewUrl` | `itunes_collection_url` |
| `collectionArtistId` | `itunes_collection_artist_id` (None if absent) |
| `collectionArtistName` | `itunes_collection_artist_name` (None if absent) |

**Fields explicitly not stored:**
- `previewUrl` — transient expiring CDN URL; must not be cached (confirmed in research)
- `currency` — not relevant
- `collectionPrice` — not relevant
- `trackPrice` — not relevant
- `trackCensoredName` — redundant with `trackName`
- `collectionCensoredName` — redundant with `collectionName`
- `wrapperType` / `kind` — used only for response validation, not stored
- `country` (response field) — the query country code is stored in `itunes_country`
  instead (more reliable than the full-name value returned in the response body)
- `collectionExplicitness` — not stored; `trackExplicitness` is sufficient

**Artwork URL transformation:**
Store `artworkUrl100` with the size segment replaced to
`{config.artwork_size}x{config.artwork_size}bb.jpg` (default `600x600bb.jpg`).
Transform by regex substitution of the terminal `/\d+x\d+bb\.jpg` segment.
This templating is community-reported and not officially documented — it is treated
as best-effort. The raw `artworkUrl100` value is not stored as a fallback; the
transformed URL is stored directly. Rationale: storing a 100px URL as a fallback
would require extra schema complexity for marginal gain. If the template breaks,
the whole artwork field goes to `None` on next re-import.

### Call 2 (optional) — lookup by stored trackId

Used only for re-lookup when `itunes_track_id` is already stored and
`config.fetch_lookup` is `True`. Replaces the keyword search entirely for that
track — it does not supplement it.

```
GET https://itunes.apple.com/lookup
    ?id={stored_track_id}
```

Extract the same field set as in Call 1.

### API call budget per track

- Fresh import: 1 call (US search) minimum; up to 3 calls if US + 2 country fallbacks
  all return zero results
- Re-lookup via ID: exactly 1 call
- Maximum: 3 calls (us → gb → de, all returning zero results)

---

## Output Schema

All keys are always present in the returned dict. `None` indicates absent/not applicable.

`itunes_confidence` and `itunes_search_strategy` and `itunes_country` and
`itunes_lookup_timestamp` are always set to a non-None string value.

| Key | Source JSON key | Python type | Nullable | Notes |
|---|---|---|---|---|
| `itunes_track_id` | `trackId` | `int` | Yes | None on no match |
| `itunes_artist_id` | `artistId` | `int` | Yes | None on no match |
| `itunes_collection_id` | `collectionId` | `int` | Yes | None on no match |
| `itunes_confidence` | (computed) | `str` | No | `"high"`, `"low"`, or `"none"` |
| `itunes_track_name` | `trackName` | `str` | Yes | None on no match |
| `itunes_artist_name` | `artistName` | `str` | Yes | None on no match |
| `itunes_collection_name` | `collectionName` | `str` | Yes | None on no match |
| `itunes_release_date` | `releaseDate` | `str` | Yes | ISO 8601 string as returned; None if absent |
| `itunes_track_time_ms` | `trackTimeMillis` | `int` | Yes | None if absent |
| `itunes_disc_count` | `discCount` | `int` | Yes | None if absent |
| `itunes_disc_number` | `discNumber` | `int` | Yes | None if absent |
| `itunes_track_count` | `trackCount` | `int` | Yes | None if absent |
| `itunes_track_number` | `trackNumber` | `int` | Yes | None if absent |
| `itunes_genre` | `primaryGenreName` | `str` | Yes | None if absent; note: too coarse for techno/house distinction |
| `itunes_track_explicit` | `trackExplicitness` | `str` | Yes | `"explicit"`, `"cleaned"`, or `"notExplicit"`; None if absent |
| `itunes_is_streamable` | `isStreamable` | `bool` | Yes | None if absent |
| `itunes_artwork_url` | `artworkUrl100` (transformed) | `str` | Yes | Template-substituted to `{artwork_size}x{artwork_size}bb.jpg`; None if absent |
| `itunes_track_url` | `trackViewUrl` | `str` | Yes | None if absent |
| `itunes_artist_url` | `artistViewUrl` | `str` | Yes | None if absent |
| `itunes_collection_url` | `collectionViewUrl` | `str` | Yes | None if absent |
| `itunes_collection_artist_id` | `collectionArtistId` | `int` | Yes | None unless Various Artists compilation |
| `itunes_collection_artist_name` | `collectionArtistName` | `str` | Yes | None unless Various Artists compilation |
| `itunes_search_strategy` | (computed) | `str` | No | `"artist_title"`, `"id"`, or `"none"` |
| `itunes_country` | (query parameter used) | `str` | No | ISO 3166-1 alpha-2 code actually used in the winning call; `"none"` when no match |
| `itunes_lookup_timestamp` | (computed) | `str` | No | ISO 8601 UTC timestamp of when the lookup was performed |
| `itunes_error` | (computed on failure) | `str` | Yes | Short error description; present only on failure path |

**`previewUrl` is explicitly excluded.** Research confirms these are transient expiring
CDN URLs. Storing them would produce stale URLs on any re-read after TTL expiry.

**Price fields (`collectionPrice`, `trackPrice`, `currency`) are explicitly excluded.**
Not relevant to Crate's use case.

---

## Error Handling

Each failure mode is handled explicitly. The function never raises.

### No match (zero search results after all strategies)
Return the no-match dict:
- All data fields set to `None`
- `itunes_confidence = "none"`
- `itunes_search_strategy = "none"`
- `itunes_country = "none"`
- `itunes_lookup_timestamp` = current UTC ISO 8601 timestamp
- `itunes_error` = absent (do not set this key)

### Low-confidence match
Return the data dict with `itunes_confidence = "low"`. All extracted fields are
populated with the best-scoring candidate's values. No error key is set.

### HTTP 403 (rate limit)
Log at `WARNING` with the request URL. Sleep 60 seconds. Retry the same request once.
If the retry also returns 403, return an error dict:
- All data fields `None`, `itunes_confidence = "none"`
- `itunes_error = "rate_limit: HTTP 403 after retry"`

### HTTP 429 (alternative rate-limit code)
Treat identically to HTTP 403. Same 60-second backoff, one retry, same error dict
on second failure.

### HTTP 400 (malformed request)
Log at `ERROR` with the full request URL. A 400 indicates a code bug (bad parameter).
Do not retry. Return error dict:
- `itunes_error = "bad_request: HTTP 400 — check request parameters"`

### HTTP 5xx (Apple service error)
Log at `WARNING`. Retry with exponential backoff: sleep 1s, retry; sleep 2s, retry;
sleep 4s, retry. After 3 failures, return error dict:
- `itunes_error = "server_error: HTTP {status} after 3 retries"`

### Network timeout (`requests.exceptions.Timeout`)
Log at `WARNING`. Do not retry (a timeout at this point suggests systemic network
issues; retrying wastes time during batch processing). Return error dict:
- `itunes_error = "timeout: request timed out"`

### Top-level fallback (all other exceptions)
Wrap the entire function body in `try/except Exception as e`. Log at `ERROR` with
the exception repr. Return error dict:
- `itunes_error = f"unexpected: {type(e).__name__}: {e}"`

### Error dict structure
An error dict has the same keys as any other return value. All data fields are `None`.
`itunes_confidence = "none"`, `itunes_search_strategy = "none"`,
`itunes_country = "none"`, `itunes_lookup_timestamp` = current UTC timestamp,
`itunes_error` = short description string.

---

## Rate Limiting

### Inter-request delay
Use a fixed delay of `config.rate_limit_delay` seconds (default `3.1`) after every
HTTP call. At 3.1 seconds per call this yields ~19 calls/minute per worker — just
under the documented ~20 req/min soft limit.

### Per-worker delay (not shared)
The delay is applied within each worker thread, not via a shared lock. At the default
2 workers, the effective call rate is up to ~38 req/min if both workers fire
simultaneously. This is slightly over the per-IP soft limit in the worst case.

If 403 responses are observed in production, lower `rate_limit_delay` or reduce
workers. For safety, a conservative starting point is to use a single worker for
the iTunes importer specifically.

The `time.sleep(config.rate_limit_delay)` call goes in a helper that wraps every
`requests.get()` call at the lowest level — applied unconditionally after every
request, regardless of success or failure.

### Session strategy
Each worker thread creates its own `requests.Session` instance (not shared across
threads). `requests.Session` is not thread-safe. Creating one per thread avoids
locking overhead and is sufficient given the low call rate. Session instances are
not long-lived — they are created per-call or per-batch, not as module-level globals.

### 403 mid-batch
When a 403 is received during a batch run, the per-request handler backs off 60
seconds and retries once (as described in Error Handling). This 60-second sleep
blocks only the worker that received the 403, not other workers. The other worker
continues processing at its own rate. If 403 responses are frequent, the user should
reduce `rate_limit_delay` until 403s stop, or reduce to 1 worker.

---

## Configuration

All tunable parameters live in a `ItunesConfig` dataclass in `backend/config.py`.
The dataclass is instantiated once at application startup and passed to `fetch_itunes`.

| Parameter | Controls | Location | Default |
|---|---|---|---|
| `user_agent` | User-Agent header sent with all requests | `ItunesConfig` | `"CrateApp/0.1 (contact@example.com)"` |
| `max_search_results` | Number of candidates fetched per search call (iTunes `limit` param) | `ItunesConfig` | `5` |
| `confidence_threshold` | Minimum total score to accept a match as `"high"` confidence | `ItunesConfig` | `0.7` |
| `duration_tolerance_seconds` | Maximum duration difference (seconds) to accept a candidate | `ItunesConfig` | `30` |
| `country_fallbacks` | Ordered list of country codes to try after US returns zero results | `ItunesConfig` | `["gb", "de"]` |
| `fetch_lookup` | Whether to use the `?id=` endpoint for re-lookups of stored `trackId` values | `ItunesConfig` | `True` |
| `artwork_size` | Pixel size for artwork URL template substitution | `ItunesConfig` | `600` |
| `rate_limit_delay` | Inter-request delay in seconds | `ItunesConfig` | `3.1` |
| `request_timeout` | `requests.get` timeout in seconds | `ItunesConfig` | `10` |

`request_timeout` is not listed in the prompt requirements but is included because
hardcoding a timeout value is a configuration smell — it is cheap to expose.

---

## Test Plan

**Location:** `backend/tests/test_importer/test_itunes.py`

**No live API calls in any test.** All HTTP is mocked with `unittest.mock.patch` or
`pytest-mock`'s `mocker.patch`. `requests.get` is patched at the point of import
in the itunes module (`backend.importer.itunes.requests.get`).

### Fixture: minimal mock track result

Define a single `MOCK_TRACK` dict in the test file (or `conftest.py`) that mirrors a
real iTunes track result object. Fields must include all keys extracted by the module:
`trackId`, `artistId`, `collectionId`, `trackName`, `artistName`, `collectionName`,
`releaseDate`, `trackTimeMillis`, `discCount`, `discNumber`, `trackCount`,
`trackNumber`, `primaryGenreName`, `trackExplicitness`, `isStreamable`,
`artworkUrl100`, `trackViewUrl`, `artistViewUrl`, `collectionViewUrl`,
`wrapperType = "track"`, `kind = "song"`. Do not include `previewUrl` by default —
add it only in the test that verifies it is not stored.

Use a `MOCK_RESPONSE` factory that returns a `Mock` whose `.json()` returns
`{"resultCount": 1, "results": [MOCK_TRACK]}` and `.status_code` is `200`.

### Happy path tests

| Test | What it verifies |
|---|---|
| `test_single_result_extracted` | One result returned → all `itunes_*` fields mapped correctly; `itunes_confidence = "high"` |
| `test_multiple_results_best_score_selected` | Three results with different durations → candidate closest to file duration is selected |
| `test_duration_within_threshold_accepted` | `trackTimeMillis` within ±30s of file duration → not rejected |
| `test_duration_outside_threshold_rejected` | `trackTimeMillis` > 30s away from file duration → candidate rejected; if only candidate, returns no-match dict |
| `test_preview_url_not_stored` | Response includes `previewUrl` → output dict has no `previewUrl` or `itunes_preview_url` key |
| `test_artwork_url_transformed` | `artworkUrl100 = ".../100x100bb.jpg"` → `itunes_artwork_url = ".../600x600bb.jpg"` |

### Country fallback tests

| Test | What it verifies |
|---|---|
| `test_us_zero_results_falls_back_to_gb` | US returns `resultCount: 0`; GB returns one result → `itunes_country = "gb"`, `itunes_search_strategy = "artist_title"` |
| `test_all_countries_zero_results` | US, GB, DE all return `resultCount: 0` → `itunes_confidence = "none"`, `itunes_search_strategy = "none"` |

### Failure path tests

| Test | What it verifies |
|---|---|
| `test_http_403_backoff_retry_success` | First call raises `HTTPError(403)`; second call succeeds → result returned, `itunes_confidence = "high"` |
| `test_http_403_backoff_retry_still_403` | Both calls raise `HTTPError(403)` → error dict returned, no exception, `itunes_error` contains `"rate_limit"` |
| `test_http_5xx_retries_then_error_dict` | Three calls each raise `HTTPError(503)` → error dict after 3 failures, no exception |
| `test_http_400_no_retry` | Call raises `HTTPError(400)` → error dict returned immediately, `requests.get` called exactly once |
| `test_timeout_returns_error_dict` | Call raises `requests.exceptions.Timeout` → error dict returned, no exception propagates |
| `test_unknown_exception_top_level_fallback` | Call raises `ValueError("unexpected")` → top-level handler catches it, error dict returned |

### Field extraction tests

| Test | What it verifies |
|---|---|
| `test_compilation_fields_stored` | Result includes `collectionArtistId` / `collectionArtistName` → stored in output |
| `test_compilation_fields_absent` | Standard non-VA result has no `collectionArtistId` → both `itunes_collection_artist_id` and `itunes_collection_artist_name` are `None` |
| `test_is_streamable_stored_as_bool` | `isStreamable: true` in response → `itunes_is_streamable == True` (Python bool) |
| `test_lookup_by_id_path` | `config.fetch_lookup = True`, stored track_id provided → lookup endpoint called, search endpoint not called |
| `test_no_duration_disables_rejection` | `duration_seconds = None` → candidate not rejected for duration mismatch; score computed from fuzzy only |

---

## Open Questions

The following are the 8 open questions from `docs/research/itunes.md`, assessed for
impact on this plan.

**1. Artwork URL templating upper bound**
Impact: Yes — the plan uses `600x600bb.jpg` substitution.
Decision: Commit to the templated URL (not the raw `artworkUrl100`). Storing a 100px
URL as a fallback adds schema complexity for marginal gain. If the templating breaks
Apple-side, the field goes to `None` on re-import and the issue will surface quickly
in testing. Use `600` as the default `artwork_size` — community reports confirm this
is reliable. Testing at `1200` is deferred to Phase 2 validation.
**Non-blocking.**

**2. `previewUrl` TTL**
Impact: Confirmed as transient expiring URLs. Decision: do not store `previewUrl`
under any circumstances. This is already reflected in the schema.
**Non-blocking — already decided.**

**3. Rate limit enforcement mechanism (per-IP vs per-account)**
Impact: Minor. The plan uses a fixed 3.1s per-worker delay. Uncertainty about
enforcement mechanism does not change this — it is a reasonable conservative choice
regardless of enforcement method. If 403s appear in Phase 2 testing, increase the
delay or reduce to 1 worker.
**Non-blocking.**

**4. `trackId` stability across re-ingests**
Impact: The plan stores `itunes_track_id` and uses it for re-lookups. If Apple
re-ingests and changes the ID, the lookup returns `resultCount: 0` and the module
falls back to returning a no-match dict for that track. This is handled gracefully.
Decision: store the ID, use it for re-lookups, but do not treat it as a permanent
stable identifier — a no-match on re-lookup is an acceptable outcome.
**Non-blocking.**

**5. Match rate on a real DJ library (30–50% estimate)**
Impact: The expected high no-match rate does not change the design. Country fallbacks
(gb, de) add at most 2 extra calls for the ~50–70% of tracks that get no match on the
US storefront. At 3.1s per call, this is acceptable overhead. If in Phase 2 testing
the fallbacks never improve the match rate, they can be disabled by setting
`country_fallbacks = []`.
**Non-blocking.**

**6. `version=1` vs `version=2`**
Impact: None. The plan uses `version=2` (the API default). No fields differ between
versions that are relevant to this module. This is confirmed as a non-blocking deferral.
**Non-blocking.**

**7. ISRC via authenticated Apple Music API**
Impact: None for this module. ISRC is not available from the iTunes Search API and
must come from MusicBrainz. The authenticated Apple Music API is out of scope for
Phase 2.
**Non-blocking — deferred to a later phase if ever needed.**

**8. Regional coverage difference for `country=de`**
Impact: The country fallback assumes `de` adds coverage for German labels (Kompakt,
Tresor). This is not confirmed by systematic testing. Decision: include `de` in the
default `country_fallbacks` list, but do not assume it will improve match rate
significantly. If Phase 2 validation shows it never helps, remove it from the default.
**Non-blocking.**

---

## Implementation Order

1. **Create `ItunesConfig` dataclass** in `backend/config.py` with all parameters
   from the Configuration section and their defaults.

2. **Write the HTTP helper** — a thin wrapper around `requests.get` that applies the
   fixed rate-limit delay after every call, sets the User-Agent header, and handles
   403/429 (60s backoff + 1 retry) and 5xx (exponential backoff, 3 retries). Returns
   the parsed JSON dict or raises the appropriate exception for the caller to handle.

3. **Write the candidate scorer** — a pure function `_score_candidate(result, artist,
   title, duration_seconds, config) -> float` that computes the weighted fuzzy + duration
   score. No I/O. Write unit tests for this function first.

4. **Write the field extractor** — a pure function `_extract_fields(result, strategy,
   country, config) -> dict` that maps the chosen iTunes result object to the
   `itunes_`-prefixed output dict. Handles missing keys with `.get()` and applies the
   artwork URL transformation. No I/O.

5. **Write the search strategy loop** — iterates us → gb → de, calls the HTTP helper,
   scores candidates, returns the best result dict or `None` for no match.

6. **Write the re-lookup path** — calls `lookup?id=` endpoint, returns the single
   result dict or `None` for not-found.

7. **Assemble `fetch_itunes`** — top-level function wrapping steps 5/6 in
   `try/except Exception`, building the final output dict, setting
   `itunes_lookup_timestamp`, and returning the correct structure for every outcome.

8. **Write tests** — cover all cases in the Test Plan. Mock `requests.get` throughout.
   Run with `pytest backend/tests/test_importer/test_itunes.py`.

9. **Wire into `pipeline.py`** — call `fetch_itunes` in the ThreadPoolExecutor
   alongside the other enrichment steps. Write the `itunes_*` fields to the database
   `INSERT OR REPLACE`.
