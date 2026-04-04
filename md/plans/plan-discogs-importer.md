# Implementation Plan: Discogs API Importer Module

## Overview

`backend/importer/discogs.py` takes structured track metadata (artist, title,
catalogue number, barcode, year) and a configured `discogs_client.Client` instance,
searches the Discogs API for the best matching release, fetches the full release
record, and returns a flat dictionary of raw API fields. The module does not compute
scores, derive features, or make curation decisions — it stores exactly what Discogs
returns and leaves interpretation to later stages. When no match is found or an error
occurs, it returns a dict with all release fields set to `None` and a status field
set explaining why. The module never raises.

---

## Function Interface

```python
def fetch_discogs_metadata(
    artist: str | None,
    title: str | None,
    catno: str | None,
    barcode: str | None,
    year: int | None,
    client: discogs_client.Client,
    config: DiscogsConfig,
) -> dict[str, object]:
```

**Inputs:**

| Parameter | Type | Source in pipeline |
|---|---|---|
| `artist` | `str \| None` | AcoustID/MusicBrainz or file tag |
| `title` | `str \| None` | AcoustID/MusicBrainz or file tag |
| `catno` | `str \| None` | File tag |
| `barcode` | `str \| None` | File tag |
| `year` | `int \| None` | AcoustID/MusicBrainz or file tag |
| `client` | `discogs_client.Client` | Created per-thread in pipeline |
| `config` | `DiscogsConfig` | Loaded from `backend/config.py` |

**Return on success:** flat dict with all schema fields populated from the matched
release.

**Return on no match:** flat dict with all release fields as `None`,
`discogs_confidence = "none"`, `discogs_search_strategy = "none"`,
`discogs_lookup_timestamp` set, no `discogs_error` field.

**Return on low-confidence match:** flat dict with all release fields populated,
`discogs_confidence = "low"`, `discogs_search_strategy` set to the strategy that
found the result.

**Return on failure:** flat dict with all release fields as `None`,
`discogs_confidence = "none"`, `discogs_error` set to the exception message string,
`discogs_lookup_timestamp` set.

**Errors:** never raised. The top-level function body is wrapped in a broad
`except Exception` that catches anything not already handled, logs it, and returns
the failure dict.

---

## Search Strategy

### Priority order

`catno` > `barcode` > `artist + title`

This matches the research doc finding: catno and barcode are unique identifiers;
artist+title is fuzzy. Each strategy is attempted in order and stops at the first
strategy that returns at least one result.

### Decision tree

```
1. If catno is known:
      search(catno=catno, type=release)
      If artist also known: search(catno=catno, artist=artist, type=release)
      → use the call that returns more results (or either if both return results)
      → actually: first try catno+artist (more specific), fall through to catno-only
        if zero results
      If results found → go to Candidate Selection
      If zero results → continue to step 2

2. If barcode is known:
      search(barcode=barcode, type=release)
      If results found → go to Candidate Selection
      If zero results → continue to step 3

3. If artist and title both known:
      search(artist=artist, release_title=title, type=release, format=Vinyl)
      If zero results:
        retry without format filter:
        search(artist=artist, release_title=title, type=release)
      If results found → go to Candidate Selection
      If zero results → continue to step 4

4. No match. Return no-match dict.
```

**`format=Vinyl` filter:** applied only on the first artist+title attempt. A DJ
library is overwhelmingly vinyl; the filter reduces noise. If it returns zero,
retry without it — the release may be a CD promo or digital reissue that is still
relevant.

**`per_page`:** always request `per_page=config.max_search_results` (default 5).
We only need to score a small candidate set; fetching 50+ results is wasteful.
Cap at 10 to stay well within the rate limit budget.

**Total search call budget per track:**

| Scenario | Search calls |
|---|---|
| catno match on first try | 1 |
| catno+artist tried, then catno-only fallback | 2 |
| catno zero, barcode match | 2 |
| catno zero, barcode zero, artist+title vinyl match | 3 |
| catno zero, barcode zero, artist+title retry without vinyl | 4 |
| Complete no match | up to 4 |

---

## Candidate Selection

### Scoring

When a search returns multiple results, score each candidate from the search result
object (not the full release — no extra API calls at this stage).

| Signal | Points | Condition |
|---|---|---|
| Catno exact match (case-insensitive) | +3 | `result.catno.lower() == catno.lower()` |
| Artist name match (case-insensitive, any in `result.title`) | +2 | `artist.lower() in result.title.lower()` |
| Year exact match | +1 | `result.year == str(year)` (search results return year as string) |
| Year within ±1 | +0.5 | `abs(int(result.year) - year) <= 1` |
| Format includes Vinyl | +1 | `"Vinyl"` in `result.format` flat array |
| Format includes `12"` | +0.5 | `'12"'` in `result.format` flat array |
| data_quality is Correct or Complete | +0.5 | value in `{"Correct", "Complete and Correct"}` |
| `community.have` > 100 | +0.25 | tiebreaker only |

**Note:** Search result objects contain `catno`, `year` (string), `format` (flat
array), `community.have`, and `community.want` — all confirmed from live API
responses in the research doc. `data_quality` is in search results for some entity
types; if absent, skip that signal.

### Confidence thresholds

| Score | `discogs_confidence` value |
|---|---|
| ≥ 3.0 | `"high"` |
| 1.0 – 2.9 | `"low"` |
| < 1.0 | treat as no match |

**Single result:** still scored. If score < 1.0, treat as no match (a single
irrelevant result is still a false positive).

**Tie:** if two candidates share the highest score, prefer the one with higher
`community.have`. If still tied, take the first result (index 0, which Discogs
returns as most relevant).

**Low-confidence match:** store the top-scoring candidate's data with
`discogs_confidence = "low"`. Do not skip — the DJ can review or override later.
A `discogs_error` field is not set for low-confidence matches (they are valid data,
just uncertain).

---

## API Call Sequence

### Call 1 (always): search

See Search Strategy above. Returns search result objects — a lightweight summary
without `artists`, `tracklist`, `identifiers`, `extraartists`, `images`, `videos`,
`companies` (confirmed absent in search results per research doc).

Fields extracted from the winning **search result** for scoring and for partial
population of the output dict:

```
result.id               → discogs_release_id (int)
result.master_id        → discogs_master_id (int, 0 means absent)
result.catno            → used in scoring; also stored as discogs_catno fallback
result.year             → used in scoring
result.data_quality     → used in scoring
result.community.have   → discogs_have
result.community.want   → discogs_want
```

### Call 2 (always on match): full release

```
GET /releases/{discogs_release_id}
```

Fields extracted from the full release response — exact JSON paths from the
research doc:

**Scalars:**

| JSON path | Dict key | Notes |
|---|---|---|
| `id` | `discogs_release_id` | Overrides search value |
| `title` | `discogs_title` | Release title (no artist prefix) |
| `year` | `discogs_year` | Integer; may be absent |
| `country` | `discogs_country` | String; may be absent |
| `released` | `discogs_released` | e.g. `"1993-07-00"`, day may be `00` |
| `released_formatted` | `discogs_released_formatted` | e.g. `"Jul 1993"` |
| `status` | `discogs_status` | Confirmed value: `"Accepted"` |
| `data_quality` | `discogs_data_quality` | Quality signal |
| `master_id` | `discogs_master_id` | Integer; absent if no master |
| `master_url` | `discogs_master_url` | String; absent if no master |
| `uri` | `discogs_url` | Full URL on www.discogs.com |
| `artists_sort` | `discogs_artists_sort` | Sort-order artist name string |
| `notes` | `discogs_notes` | Free text; may be absent or long |
| `num_for_sale` | `discogs_num_for_sale` | Marketplace integer |
| `lowest_price` | `discogs_lowest_price` | Float or null |

**`artists` array** — primary artist credits:

Extract `name` for each entry. Join with `artists[n].join` phrase to reconstruct
the credited artist string:
```
discogs_artists         → JSON list of name strings, e.g. ["Jeff Mills"]
discogs_artists_sort    → from top-level artists_sort field
```

**`labels` array** — use index 0 (primary label) for the flat fields:

| JSON path | Dict key | Notes |
|---|---|---|
| `labels[0].id` | `discogs_label_id` | Integer |
| `labels[0].name` | `discogs_label` | Primary label name |
| `labels[0].catno` | `discogs_catno` | Catalogue number; may be empty string → store as None |
| `labels[0].entity_type_name` | `discogs_label_entity_type` | e.g. `"Label"` |

Store the full `labels` array as `discogs_labels_raw` (JSON) so no label data is
lost if there are multiple labels or distributors.

**`extraartists` array** — credited personnel:

Filter by `role` field:

Producer roles — match if role contains any of:
`"Producer"`, `"Co-producer"`, `"Executive Producer"`, `"Produced By"`
```
discogs_producers       → JSON list of name strings
```

Remixer roles — match if role contains any of:
`"Remix"`, `"Remixed By"`, `"Re-Mix"`, `"Remix By"`
```
discogs_remixers        → JSON list of name strings
```

Store the full `extraartists` array as `discogs_extraartists_raw` (JSON) so
engineer, mastering, design credits are not discarded:
```
discogs_extraartists_raw → JSON list of {name, role} dicts
```

**`formats` array:**

```
discogs_format_names    → JSON list of unique name strings, e.g. ["Vinyl"]
discogs_format_descs    → JSON flat list, all descriptions merged, e.g. ["12\"", "33 ⅓ RPM", "Promo"]
```

Merge all `formats[n].descriptions` arrays into a single flat list (deduplication
not required — preserve the raw merged output).

**`genres` and `styles`:**

```
discogs_genres          → JSON list of strings, e.g. ["Electronic"]
discogs_styles          → JSON list of strings, e.g. ["Techno", "Tribal"]
```

Store empty list `[]` if absent (the field exists but may be empty per research doc).

**`tracklist` array:**

Extract only: `position`, `title`, `duration`, `type_`. Omit `artists` and
`extraartists` (per-track credits are rarely needed and inflate storage).
```
discogs_tracklist       → JSON list of {position, title, duration, type_} dicts
```
Only include entries where `type_ == "track"` (exclude `"heading"` and `"index"`
entries per research doc).

**`identifiers` array:**

```
discogs_barcodes        → JSON list of value strings where type == "Barcode"
discogs_matrix_numbers  → JSON list of value strings where type == "Matrix / Runout"
```

**`community` object:**

| JSON path | Dict key |
|---|---|
| `community.have` | `discogs_have` |
| `community.want` | `discogs_want` |
| `community.rating.count` | `discogs_rating_count` |
| `community.rating.average` | `discogs_rating_avg` |

### Call 3 (conditional): master release

**When to fetch:** `config.fetch_master is True` AND `discogs_master_id` is present
and non-zero.

**What it adds** that the release does not already contain:
- `master.year` — year of the **first** release across all pressings (may be earlier
  than the specific release year; useful for original release date)
- `master.most_recent_release` — ID of the most recent version

These two fields justify a master fetch when the config flag is on. The master's
`genres`, `styles`, and `tracklist` are redundant with the release response.

Fields extracted:

| JSON path | Dict key |
|---|---|
| `master.year` | `discogs_master_year` |
| `master.most_recent_release` | `discogs_master_most_recent_id` |

If master fetch is disabled or `master_id` is absent/zero: both keys are set to
`None`.

### Call 4 (conditional): label

**Decision: do not fetch the label endpoint by default.**

The research doc confirms that `labels[0].name` and `labels[0].catno` are already
present in the full release response. The label endpoint adds `parent_label`,
`sublabels`, and `profile` text — not needed for Phase 2. The `fetch_label` config
flag exists but defaults to `False`. Defer until there is a specific use case.

### Total API call budget per track

| Scenario | Total calls |
|---|---|
| catno match, no master fetch | 2 |
| catno match, with master fetch | 3 |
| Artist+title with vinyl retry, with master fetch | 5 |
| No match (all strategies exhausted) | 2–4 (searches only) |

---

## Output Schema

Full flat dictionary. All keys always present in the return value; nullable fields
set to `None` when absent.

| Key | Source | Type | Nullable | Notes |
|---|---|---|---|---|
| `discogs_release_id` | `release.id` | `int` | Yes | None on no match |
| `discogs_master_id` | `release.master_id` | `int` | Yes | None if absent or zero |
| `discogs_confidence` | computed | `str` | No | `"high"`, `"low"`, or `"none"` |
| `discogs_search_strategy` | computed | `str` | No | `"catno"`, `"barcode"`, `"artist_title"`, or `"none"` |
| `discogs_url` | `release.uri` | `str` | Yes | Full discogs.com URL |
| `discogs_title` | `release.title` | `str` | Yes | |
| `discogs_year` | `release.year` | `int` | Yes | |
| `discogs_country` | `release.country` | `str` | Yes | |
| `discogs_released` | `release.released` | `str` | Yes | May have `00` day |
| `discogs_released_formatted` | `release.released_formatted` | `str` | Yes | |
| `discogs_status` | `release.status` | `str` | Yes | |
| `discogs_data_quality` | `release.data_quality` | `str` | Yes | |
| `discogs_notes` | `release.notes` | `str` | Yes | Free text |
| `discogs_artists_sort` | `release.artists_sort` | `str` | Yes | |
| `discogs_num_for_sale` | `release.num_for_sale` | `int` | Yes | |
| `discogs_lowest_price` | `release.lowest_price` | `float` | Yes | USD; null when none listed |
| `discogs_label_id` | `labels[0].id` | `int` | Yes | |
| `discogs_label` | `labels[0].name` | `str` | Yes | Primary label name |
| `discogs_catno` | `labels[0].catno` | `str` | Yes | None if empty string |
| `discogs_label_entity_type` | `labels[0].entity_type_name` | `str` | Yes | |
| `discogs_artists` | `artists[].name` | `list[str]` | Yes | JSON |
| `discogs_genres` | `release.genres` | `list[str]` | Yes | JSON; `[]` if absent |
| `discogs_styles` | `release.styles` | `list[str]` | Yes | JSON; `[]` if absent |
| `discogs_format_names` | `formats[].name` | `list[str]` | Yes | JSON |
| `discogs_format_descs` | `formats[].descriptions` (merged) | `list[str]` | Yes | JSON flat list |
| `discogs_producers` | `extraartists` filtered by role | `list[str]` | Yes | JSON |
| `discogs_remixers` | `extraartists` filtered by role | `list[str]` | Yes | JSON |
| `discogs_extraartists_raw` | `extraartists[]` `{name, role}` | `list[dict]` | Yes | JSON |
| `discogs_labels_raw` | `labels[]` all entries | `list[dict]` | Yes | JSON |
| `discogs_tracklist` | `tracklist[]` type==track only | `list[dict]` | Yes | JSON; `{position, title, duration, type_}` |
| `discogs_barcodes` | `identifiers[]` type==Barcode | `list[str]` | Yes | JSON |
| `discogs_matrix_numbers` | `identifiers[]` type==Matrix / Runout | `list[str]` | Yes | JSON |
| `discogs_have` | `community.have` | `int` | Yes | |
| `discogs_want` | `community.want` | `int` | Yes | |
| `discogs_rating_avg` | `community.rating.average` | `float` | Yes | Observed scale 1–5 |
| `discogs_rating_count` | `community.rating.count` | `int` | Yes | |
| `discogs_master_year` | `master.year` | `int` | Yes | None if not fetched |
| `discogs_master_most_recent_id` | `master.most_recent_release` | `int` | Yes | None if not fetched |
| `discogs_master_url` | `release.master_url` | `str` | Yes | None if no master |
| `discogs_lookup_timestamp` | computed | `str` | No | ISO 8601, always set |
| `discogs_error` | computed | `str` | Yes | Set only on failure |

**Total keys: 43.**

**JSON fields** (stored as serialised strings in SQLite): `discogs_artists`,
`discogs_genres`, `discogs_styles`, `discogs_format_names`, `discogs_format_descs`,
`discogs_producers`, `discogs_remixers`, `discogs_extraartists_raw`,
`discogs_labels_raw`, `discogs_tracklist`, `discogs_barcodes`,
`discogs_matrix_numbers`.

---

## Error Handling

| Failure mode | Behaviour |
|---|---|
| Zero search results after all strategies | Return no-match dict. `discogs_confidence = "none"`, `discogs_search_strategy = "none"`. Log at `DEBUG` (expected for white labels/promos). |
| Candidate score < 1.0 (single or multi result) | Treat as no match. Same return as above. Log at `DEBUG`. |
| Low-confidence match (score 1.0–2.9) | Return populated dict with `discogs_confidence = "low"`. No error field. Log at `INFO` with match details. |
| `discogs_client.exceptions.HTTPError` (404) | Log at `DEBUG`. Return no-match dict (404 = release ID doesn't exist; not an infrastructure error). |
| `discogs_client.exceptions.HTTPError` (4xx other) | Log at `WARNING`. Return failure dict with `discogs_error` set. |
| `discogs_client.exceptions.HTTPError` (5xx) | Log at `WARNING`. Return failure dict with `discogs_error` set. |
| `discogs_client.exceptions.TooManyAttemptsError` | Built-in backoff exhausted. Log at `WARNING`. Return failure dict with `discogs_error = "rate limit: max retries exceeded"`. |
| `discogs_client.exceptions.AuthorizationError` | Token invalid or expired. Log at `ERROR`. Return failure dict. This is a configuration error — it will affect all tracks. |
| `discogs_client.exceptions.ConfigurationError` | Log at `ERROR`. Return failure dict. |
| Network timeout / `requests.exceptions.Timeout` | Log at `WARNING`. Return failure dict with `discogs_error` set. |
| `KeyError` / `AttributeError` on field extraction | Per-field: catch, set that key to `None`, log at `DEBUG` with field name. Continue extraction of remaining fields. Do not abort the whole extraction. |
| Any other `Exception` (top-level) | Log at `ERROR` with traceback. Return failure dict. Never raise. |

**Failure dict:** all release fields are `None`, `discogs_confidence = "none"`,
`discogs_search_strategy` set if a strategy was underway when the error occurred,
`discogs_error` = exception message string, `discogs_lookup_timestamp` = now.

---

## Rate Limiting

### Client instance strategy

**One `discogs_client.Client` instance per thread.** Thread safety of
python3-discogs-client is not confirmed in the research doc (open question 2).
Creating one instance per thread eliminates the risk. The pipeline calls
`fetch_discogs_metadata(...)` with a per-thread client passed in as an argument,
created in the `ThreadPoolExecutor` initializer.

```python
# In pipeline.py — initializer for the thread pool
def _thread_init():
    threading.local().discogs_client = discogs_client.Client(
        config.user_agent,
        user_token=config.discogs_token,
    )
```

The `discogs.py` module itself does not create clients — it accepts one as a
parameter.

### Built-in backoff

`python3-discogs-client` has built-in automatic backoff on rate limit hits, enabled
by default. **Do not disable it.** The module does not implement additional
application-level throttling — the library's backoff is sufficient for 2 workers.

At 2 workers × ~3 calls/track × ~1 track/2s processing time = ~3 calls/s = 180
calls/min, which exceeds the 60 req/min limit. **The built-in backoff will engage
regularly during bulk imports.** This is expected and acceptable — it serialises
the requests and slows the import, which is fine for a background pipeline.

### Rate limit header monitoring

Do not inspect `X-Discogs-Ratelimit-Remaining` in the module. The library's backoff
handles it. If the pipeline needs to display progress/ETA, it can do so from
elapsed time without consulting rate limit headers.

### `TooManyAttemptsError`

If raised, log at `WARNING`, return failure dict for that track, and continue with
the next track. Do not abort the entire import. The pipeline will retry failed tracks
if a retry mechanism is implemented (Phase 2 detail — not in scope here).

---

## Configuration

All configuration lives in a `DiscogsConfig` dataclass in `backend/config.py`,
loaded from environment variables and `.env`.

| Parameter | Controls | Location | Default |
|---|---|---|---|
| `discogs_token` | Personal access token for auth | `backend/config.py` from `DISCOGS_TOKEN` env var | `None` (unauthenticated, 25 req/min) |
| `user_agent` | User-Agent header for all requests | `backend/config.py` from `DISCOGS_APP` env var | `"CrateApp/0.1 (your@email.com)"` |
| `max_search_results` | Max candidates to score per search call (`per_page`) | `DiscogsConfig` | `5` |
| `confidence_threshold_high` | Minimum score for `"high"` confidence | `DiscogsConfig` | `3.0` |
| `confidence_threshold_low` | Minimum score for `"low"` confidence (below = no match) | `DiscogsConfig` | `1.0` |
| `fetch_master` | Whether to make the optional master release API call | `DiscogsConfig` | `False` |
| `fetch_label` | Whether to make the optional label API call | `DiscogsConfig` | `False` |
| `vinyl_filter_first` | Whether to add `format=Vinyl` on first artist+title search | `DiscogsConfig` | `True` |

`discogs_token` must never be hardcoded. If `None`, the client operates
unauthenticated at 25 req/min.

---

## Test Plan

### Fixture strategy

**No live API calls in any test.** All HTTP is mocked using `unittest.mock.patch`
or `pytest-mock`. Mock the `discogs_client.Client` object and configure it to return
mock `Release`, `MasterRelease`, and search result objects.

**Minimal mock release fixture:**

```python
@pytest.fixture
def mock_release():
    release = MagicMock()
    release.id = 616407
    release.title = "The Bells (10th Anniversary)"
    release.year = 2006
    release.country = "US"
    release.released = "2006-00-00"
    release.released_formatted = "2006"
    release.status = "Accepted"
    release.data_quality = "Correct"
    release.master_id = 449968
    release.master_url = "https://api.discogs.com/masters/449968"
    release.uri = "/release/616407-Jeff-Mills-The-Bells-10th-Anniversary"
    release.artists_sort = "Mills, Jeff"
    release.notes = ""
    release.num_for_sale = 10
    release.lowest_price = 25.0
    release.artists = [MagicMock(name="Jeff Mills", join="")]
    release.labels = [MagicMock(id=123, name="Purpose Maker", catno="PM-020",
                                entity_type_name="Label")]
    release.genres = ["Electronic"]
    release.styles = ["Techno", "Tribal"]
    release.formats = [{"name": "Vinyl", "qty": "1",
                        "descriptions": ['12"', "33 \u2153 RPM"]}]
    release.extraartists = []
    release.tracklist = [MagicMock(position="A", title="The Bells",
                                   duration="9:05", type_="track")]
    release.identifiers = [MagicMock(type="Barcode", value="PM 020-A")]
    release.community = MagicMock(have=1423, want=2246,
                                  rating=MagicMock(average=4.2, count=88))
    release.labels  # labels is a list, access .data for raw dict if needed
    return release
```

**Minimal mock search result fixture** (search result objects have fewer fields than
full releases — confirmed from research doc):

```python
@pytest.fixture
def mock_search_result():
    result = MagicMock()
    result.id = 616407
    result.title = "Jeff Mills - The Bells (10th Anniversary)"
    result.catno = "PM-020"
    result.year = "2006"
    result.format = ["Vinyl", '12"', "33 \u2153 RPM"]
    result.data_quality = "Correct"
    result.master_id = 449968
    result.master_url = "https://api.discogs.com/masters/449968"
    result.community = MagicMock(have=1423, want=2246)
    return result
```

### Test cases

**Happy path — catno match:**
- Search with `catno="PM-020"` returns `[mock_search_result]`
- `client.release(616407)` returns `mock_release`
- Assert `result["discogs_release_id"] == 616407`
- Assert `result["discogs_confidence"] == "high"` (catno exact match = +3 points)
- Assert `result["discogs_search_strategy"] == "catno"`
- Assert `result["discogs_label"] == "Purpose Maker"`
- Assert `result["discogs_catno"] == "PM-020"`
- Assert `result["discogs_styles"] == '["Techno", "Tribal"]'` (JSON string)

**Happy path — barcode fallback:**
- catno search returns `[]`
- barcode search returns `[mock_search_result]`
- Assert `result["discogs_search_strategy"] == "barcode"`

**Happy path — artist+title fallback with vinyl retry:**
- catno and barcode both `None`
- artist+title with `format=Vinyl` returns `[]`
- artist+title without format filter returns `[mock_search_result]`
- Assert `result["discogs_search_strategy"] == "artist_title"`

**Candidate scoring — multiple results:**
- Search returns two results: one with catno match (score 3.0+), one without
- Assert highest-scoring result is selected
- Assert `discogs_confidence == "high"`

**Low-confidence match:**
- Single result with artist partial match only (score ~2.0)
- Assert `discogs_confidence == "low"`
- Assert release fields are populated (data is stored despite low confidence)

**No match — all strategies exhausted:**
- All searches return `[]`
- Assert all release fields are `None`
- Assert `discogs_confidence == "none"`
- Assert `discogs_search_strategy == "none"`
- Assert `"discogs_error"` is not in result (no match ≠ error)

**Score below threshold — single irrelevant result:**
- Search returns one result with score < 1.0 (no artist, catno, or year match)
- Assert treated as no match

**Field extraction — extraartists filtering:**
- `mock_release.extraartists` contains `[{name: "X", role: "Producer"}, {name: "Y", role: "Design"}]`
- Assert `result["discogs_producers"] == '["X"]'`
- Assert `"Y"` not in `result["discogs_producers"]`

**Field extraction — format_descs merging:**
- Release has two format objects each with descriptions
- Assert `discogs_format_descs` is a flat merged JSON list

**Field extraction — empty catno:**
- `labels[0].catno == ""` (empty string)
- Assert `result["discogs_catno"] is None`

**Failure — HTTPError 404:**
- `client.release(...)` raises `HTTPError` with status 404
- Assert result is a failure dict
- Assert `"discogs_error"` is set
- Assert no exception propagates

**Failure — TooManyAttemptsError:**
- Search raises `TooManyAttemptsError`
- Assert result is a failure dict with `discogs_error` containing "rate limit"
- Assert no exception propagates

**Failure — unexpected exception:**
- `client.release(...)` raises `RuntimeError("unexpected")`
- Assert top-level handler catches it
- Assert result is a failure dict
- Assert no exception propagates

**Master fetch enabled:**
- `config.fetch_master = True`, `mock_release.master_id = 449968`
- Mock `client.master(449968)` returns mock master with `year=1996`
- Assert `result["discogs_master_year"] == 1996`

**Master fetch disabled:**
- `config.fetch_master = False`
- Assert `client.master` is never called
- Assert `result["discogs_master_year"] is None`

---

## Open Questions

### 1. Search authentication requirement (research doc Q1)
**Status: does not block.** Live testing on 2026-04-04 showed unauthenticated search
working at 25 req/min. The plan assumes authenticated access (personal token) in
production to get 60 req/min. Unauthenticated is a fallback if no token is
configured. **Interim decision:** always use authenticated for production.

### 2. Thread safety of python3-discogs-client (research doc Q2 — implied)
**Status: does not block.** Addressed by the per-thread client instance strategy.
One `Client` per thread eliminates any shared state risk. **Interim decision:**
create one client per thread in the `ThreadPoolExecutor` initializer.

### 3. `master_id` absent vs. zero in full release endpoint (research doc Q8)
**Status: does not block.** The research doc confirms `master_id = 0` in search
results when no master exists. It notes that `master_id` may be absent (not 0) in
the full release endpoint. **Interim decision:** treat both absent and zero as "no
master" using `release.data.get("master_id") or None` (covers both cases).

### 4. Match rate for DJ library (research doc Q3)
**Status: does not block.** Estimated 50–75% overall for a techno/house library.
This means roughly 1 in 4 tracks will return a no-match dict — that's expected
behaviour, not a failure. The module is designed for graceful no-match returns.
**Interim decision:** defer validation to Phase 2 real-track testing.

### 5. Image 403 errors (research doc Q4)
**Status: deferred.** Not storing images in Phase 2. `images` are not extracted
from the release response. Revisit in Phase 5 if cover art display is added.

### 6. `status` values beyond "Accepted" (research doc Q2)
**Status: does not block.** Only `"Accepted"` releases are returned by the API in
normal operation. The module stores `release.status` as-is without filtering.
No action needed.

### 7. `community.rating` scale (research doc Q7)
**Status: does not block.** Observed range suggests 1–5 scale. Stored as raw float.
No scale assumption is made in the module. **Interim decision:** store and label as
`discogs_rating_avg`; note unconfirmed scale in schema documentation.

### 8. Search returns only first page (new)
The module requests `per_page=config.max_search_results` (default 5) and only
evaluates page 1. No pagination of search results is implemented. For catno and
barcode searches this is fine (highly specific queries). For artist+title searches
on common artists, the best match may not be in the first 5 results.
**Interim decision:** accept this limitation for Phase 2. If false-negative rate
is high on artist+title searches, raise `max_search_results` to 10 or 20 during
Phase 2 validation.

---

## Implementation Order

1. **Create `DiscogsConfig` dataclass** in `backend/config.py` with all parameters
   from the Configuration section. Load `DISCOGS_TOKEN` and `DISCOGS_APP` from env.

2. **Scaffold `backend/importer/discogs.py`** with the function signature, the
   no-match dict helper, and the failure dict helper. Both helpers return all 43
   schema keys with appropriate defaults.

3. **Implement search strategy** — the decision tree with catno → barcode →
   artist+title fallback. Each strategy calls `client.search(...)` with the
   parameters specified above.

4. **Implement candidate scoring** — the point-based scoring function that operates
   on search result objects. Returns `(best_result, score)`.

5. **Implement full release extraction** — call `client.release(id)`, extract all
   scalar fields, then extract each complex field (artists, labels, extraartists,
   formats, genres, styles, tracklist, identifiers, community).

6. **Implement extraartist role filtering** — `_extract_producers` and
   `_extract_remixers` helpers that filter `extraartists` by role substring.

7. **Implement master fetch** (conditional) — if `config.fetch_master` and
   `master_id` is present and non-zero, call `client.master(master_id)` and
   extract `year` and `most_recent_release`.

8. **Add per-field exception handling** — wrap each field extraction in try/except
   to catch `KeyError`/`AttributeError`, log at DEBUG, and set that key to `None`.

9. **Add top-level exception handling** — wrap the entire function body in
   `except Exception` to guarantee the function never raises.

10. **Write tests** in `backend/tests/test_importer/test_discogs.py` following the
    test plan. All HTTP mocked. Run `pytest` to confirm all pass.

11. **Manual smoke test** — configure a real token in `.env`, call the module
    against 5–10 known tracks (with catno, without catno, white label) to verify
    the search strategy and field extraction against live Discogs data.
