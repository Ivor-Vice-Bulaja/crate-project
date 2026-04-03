# Implementation Plan: AcoustID + MusicBrainz Lookup Module

## Overview

`backend/importer/acoustid.py` takes a file path and returns a flat dictionary of
identification and metadata fields sourced from AcoustID fingerprinting and a
MusicBrainz recording lookup. It does not compute derived scores, select crate
membership, or write to the database. On any failure it returns a dict rather than
raising, so the pipeline can always write a partial result.

---

## Function Interface

```python
def identify_track(
    file_path: str,
    config: AcoustIDConfig,
) -> dict:
    ...
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `file_path` | `str` | Absolute path to the audio file |
| `config` | `AcoustIDConfig` | Dataclass of all tuneable settings (see Configuration) |

### Return contract

| Situation | Return value |
|---|---|
| Full success | Dict with all keys populated |
| Partial failure (fingerprint OK; MusicBrainz call fails) | Dict with MusicBrainz keys set to `None`; AcoustID keys populated; no `lookup_error` field |
| AcoustID no-match (`results: []`) | Dict with all identification keys set to `None`; `acoustid_match = False`; no `lookup_error` |
| Total failure (file cannot be fingerprinted) | Dict with every key set to `None` plus `lookup_error: str` |
| Unexpected top-level exception | Same as total failure — the outer try/except ensures the function never raises |

Errors are **returned as structured data**, never raised. The caller in `pipeline.py`
should never need to wrap this function in its own try/except.

---

## Fingerprinting

```python
duration, fingerprint = acoustid.fingerprint_file(file_path)
```

- Uses `pyacoustid.fingerprint_file` with `maxlength=120` (default).
- Tries the Chromaprint C library first; falls back to `fpcalc` subprocess.
- If `NoBackendError` is raised: set `lookup_error = "fpcalc and Chromaprint library not found"` and return immediately. This is a fatal configuration error; do not attempt subsequent steps.
- If `FingerprintGenerationError` is raised: set `lookup_error = str(exception)` and return immediately. This means the file could not be decoded.
- On success: proceed to AcoustID lookup.

---

## AcoustID Lookup

```python
response = acoustid.lookup(
    apikey=config.acoustid_api_key,
    fingerprint=fingerprint,
    duration=int(duration),
    meta=["recordings", "releasegroups"],
    timeout=config.acoustid_timeout,
)
```

- `meta=["recordings", "releasegroups"]` returns recording objects with embedded release group title and type, avoiding a second API call for album type.
- pyacoustid enforces 3 req/s internally via a thread-safe lock. No manual sleep needed.
- **On `WebServiceError`**: retry once after a 2-second sleep. If the retry also fails, set all AcoustID and MusicBrainz keys to `None` and set `lookup_error = str(exception)`. Return immediately.
- **On empty results (`response["results"] == []`)**: set `acoustid_match = False`, all identification keys to `None`. Return the dict — this is a normal no-match, not an error.
- **On success**: proceed to result extraction.

### Extracting the Best Result

```python
results = response.get("results", [])
best = max(results, key=lambda r: r["score"])
acoustid_id = best["id"]
acoustid_score = best["score"]

recordings = best.get("recordings", [])
if not recordings:
    # Fingerprint found but not linked to any MusicBrainz recording
    # Store acoustid_id + acoustid_score; set mb_recording_id = None; return
```

When `results` has multiple entries, take the highest-scoring one. When a result has
multiple `recordings`, take `recordings[0]`. Multiple recordings represent alternative
interpretations of the same fingerprint — the first is conventionally most reliable
but this is unconfirmed (Open Question Q3).

---

## MusicBrainz Recording Lookup

```python
import musicbrainzngs
musicbrainzngs.set_useragent("CrateApp", "0.1", config.mb_contact)

result = musicbrainzngs.get_recording_by_id(
    mb_recording_id,
    includes=["artist-credits", "releases", "isrcs", "tags", "genres"]
)
recording = result["recording"]
```

- `set_useragent` must be called once before any API call. Call it at module level or
  in the function before the first request — but not inside a loop.
- musicbrainzngs does **not** enforce the 1 req/s rate limit internally. Add
  `time.sleep(1)` before this call if `config.mb_rate_limit` is `True` (default `True`).
- **On `ResponseError` (404)**: recording has been deleted or merged in MusicBrainz.
  Store `mb_recording_id` but set all MB metadata fields to `None`. Do not set
  `lookup_error`.
- **On `NetworkError`**: retry once after 3 seconds. If retry fails, set all MB fields
  to `None`. Do not set `lookup_error`.
- **On any other exception**: set all MB fields to `None`; log `WARNING`; continue to
  return the dict with AcoustID fields intact.

### Extracting Fields from the Recording Response

```python
# Title
title = recording.get("title")

# Duration (MB returns milliseconds; convert to seconds)
length_ms = recording.get("length")
mb_duration_s = round(length_ms / 1000, 3) if length_ms else None

# First release year
first_date = recording.get("first-release-date", "")
year = int(first_date[:4]) if first_date and len(first_date) >= 4 else None

# Artist (assemble from credits array with join phrases)
credits = recording.get("artist-credit", [])
artist = "".join(c.get("name", "") + c.get("joinphrase", "") for c in credits).strip() or None

# Artist MBID (first credited artist)
mb_artist_id = credits[0]["artist"]["id"] if credits else None

# Artist sort name
artist_sort_name = credits[0]["artist"].get("sort-name") if credits else None

# ISRC (first one only; often absent for electronic music)
isrcs = recording.get("isrcs", [])
isrc = isrcs[0] if isrcs else None

# Genres and tags (community-contributed; sparse for electronic music)
genres = [g["name"] for g in recording.get("genres", [])]
tags = [t["name"] for t in recording.get("tags", [])]

# Select best release for label/catalogue lookup
releases = recording.get("releases", [])
best_release = _select_best_release(releases)
mb_release_id = best_release["id"] if best_release else None
mb_release_title = best_release.get("title") if best_release else None
release_country = best_release.get("country") if best_release else None
release_status = best_release.get("status") if best_release else None
```

#### Release Selection Logic (`_select_best_release`)

Used to pick a single release for label/catalogue enrichment. Implemented as a
module-level helper (not inside `identify_track`).

Priority order:
1. Official releases with a known date — pick earliest by `date` string (lexicographic
   sort is safe since dates are ISO format YYYY, YYYY-MM, or YYYY-MM-DD).
2. Official releases without a date — pick the first.
3. Any release with a date — pick earliest.
4. Any release — pick the first.
5. No releases — return `None`.

---

## MusicBrainz Release Lookup (Optional)

A separate second API call to get label and catalogue number. Only made if
`config.fetch_label` is `True` (default `True`) and `mb_release_id` is not `None`.

```python
time.sleep(1)  # Always sleep before second MB call
release_result = musicbrainzngs.get_release_by_id(
    mb_release_id,
    includes=["labels"]
)
release = release_result["release"]
label_info = release.get("label-info", [])
if label_info:
    label = label_info[0].get("label", {}).get("name")
    catalogue_number = label_info[0].get("catalog-number")  # American spelling
else:
    label = None
    catalogue_number = None
```

- **On any exception**: log `WARNING`; set `label = None`, `catalogue_number = None`.
  Do not set `lookup_error`. The recording metadata is still valid.
- The field name in the MusicBrainz JSON is `catalog-number` (American spelling), not
  `catalogue-number`.

---

## Output Schema

| Key | Source | Python type | Notes | Nullable? |
|---|---|---|---|---|
| `acoustid_id` | AcoustID result | `str` | AcoustID UUID | None if no match or fingerprint failed |
| `acoustid_score` | AcoustID result | `float` | Range 0.0–1.0; no official reliability threshold | None if no match or fingerprint failed |
| `acoustid_match` | Derived | `bool` | `True` if `results` non-empty; `False` on no-match | Always set (never None) |
| `mb_recording_id` | AcoustID recording | `str` | MusicBrainz recording UUID | None if no match or fingerprint not linked to MB |
| `mb_release_id` | MusicBrainz recording | `str` | MBID of the selected release | None if no releases linked |
| `mb_artist_id` | MusicBrainz recording | `str` | First credited artist MBID | None if MB lookup failed |
| `title` | MusicBrainz recording | `str` | Recording title | None if MB lookup failed |
| `artist` | MusicBrainz recording | `str` | Full credited artist string (join phrases applied) | None if MB lookup failed |
| `artist_sort_name` | MusicBrainz recording | `str` | First artist's sort-order name | None if MB lookup failed |
| `year` | MusicBrainz recording | `int` | Year from `first-release-date` | None if date absent or MB failed |
| `mb_duration_s` | MusicBrainz recording | `float` | Duration in seconds (converted from milliseconds) | None if absent |
| `isrc` | MusicBrainz recording | `str` | First ISRC; often absent for electronic music | None if absent |
| `mb_release_title` | MusicBrainz release | `str` | Title of the selected release | None if no releases |
| `release_status` | MusicBrainz release | `str` | `"Official"`, `"Promotion"`, `"Bootleg"`, `"Pseudo-Release"` | None if absent |
| `release_country` | MusicBrainz release | `str` | ISO 3166-1 code | None if absent or worldwide |
| `mb_release_group_type` | AcoustID release group | `str` | `"Album"`, `"Single"`, `"EP"`, etc. | None if releasegroup not linked |
| `label` | MusicBrainz release lookup | `str` | Label name from `label-info[0]` | None if absent or fetch disabled |
| `catalogue_number` | MusicBrainz release lookup | `str` | Catalogue number from `label-info[0].catalog-number` | None if absent or fetch disabled |
| `genres` | MusicBrainz recording | `list[str]` | Genre name strings ← JSON | None if MB failed; `[]` if none |
| `tags` | MusicBrainz recording | `list[str]` | Community tag name strings ← JSON | None if MB failed; `[]` if none |
| `lookup_error` | Internal | `str` | Error message | Only set on total failure |

`acoustid_match` is the only field guaranteed to always be a non-None value. All other
fields may be `None`. `lookup_error` is present only on total failure (fingerprinting
failed or fpcalc not found); it is absent on no-match and partial failures.

---

## Error Handling

| Failure mode | Strategy |
|---|---|
| `NoBackendError` from `fingerprint_file` | Set `lookup_error`; return immediately. Fatal — fpcalc not installed |
| `FingerprintGenerationError` from `fingerprint_file` | Set `lookup_error`; return immediately. File could not be decoded |
| AcoustID `WebServiceError` | Retry once after 2s sleep; if retry fails, set `lookup_error`; return |
| AcoustID returns `results: []` | Set `acoustid_match = False`; all ID keys `None`; return (not an error) |
| AcoustID result has no `recordings` | Store `acoustid_id` and `acoustid_score`; `mb_recording_id = None`; return |
| MusicBrainz `ResponseError` (404) | Store `mb_recording_id`; all MB metadata fields `None`; log `WARNING`; continue |
| MusicBrainz `NetworkError` | Retry once after 3s; if retry fails, all MB fields `None`; log `WARNING`; continue |
| Release lookup fails (any exception) | `label = None`, `catalogue_number = None`; log `WARNING`; continue |
| Any missing field in MB response | Use `.get()` with `None` default; never raise |
| Top-level unexpected exception | Outermost try/except; set all keys `None`; set `lookup_error`; always return a dict |

The function must never raise.

---

## Rate Limiting

| Service | Limit | Enforcement |
|---|---|---|
| AcoustID | 3 req/s | Enforced internally by pyacoustid. No manual sleep needed |
| MusicBrainz recording lookup | 1 req/s (averaged) | **Not** enforced by musicbrainzngs. Sleep `time.sleep(1)` before each call when `config.mb_rate_limit` is `True` |
| MusicBrainz release lookup | 1 req/s (averaged) | Same — sleep before calling |

Rate limiting is enforced per process. If the pipeline runs concurrent workers
(max 2 per CLAUDE.md), the shared `time.sleep(1)` does not prevent both workers from
firing simultaneously. Mitigation: use a shared threading lock around MusicBrainz
calls if rate limit 503s are observed in Phase 2 testing. Do not pre-emptively add
a lock — measure first.

---

## Thread Safety

- All algorithm instances and API state are local to each `identify_track` call.
- The `musicbrainzngs.set_useragent` call sets global module state. Call it once at
  module import time (module-level `_setup_musicbrainz(config)` called on first use
  via a flag), not inside `identify_track`.
- pyacoustid's rate-limit lock is already thread-safe.
- MusicBrainz sleep: a bare `time.sleep(1)` in two concurrent workers means both can
  fire within the same 1-second window. Add a threading lock if 503 errors appear.

---

## Configuration

All tuneable values live in an `AcoustIDConfig` dataclass in `backend/config.py`.

| Parameter | Controls | Default |
|---|---|---|
| `acoustid_api_key` | AcoustID application API key | Required — no default |
| `acoustid_timeout` | Request timeout in seconds for AcoustID API | `10` |
| `mb_contact` | Email or URL for MusicBrainz User-Agent header | Required — no default |
| `mb_rate_limit` | Whether to sleep 1s before each MusicBrainz call | `True` |
| `fetch_label` | Whether to make the second MB call for label/catalogue | `True` |

---

## Test Plan

Tests live in `backend/tests/test_importer/test_acoustid.py`.

### Mocking strategy

All network calls are mocked. No real HTTP requests in any test.

```python
# Example fixture
@pytest.fixture
def mock_acoustid_response():
    return {
        "status": "ok",
        "results": [{
            "id": "test-acoustid-uuid",
            "score": 0.95,
            "recordings": [{
                "id": "test-mb-recording-uuid",
                "title": "Test Track",
                "duration": 300,
                "artists": [{"id": "test-artist-uuid", "name": "Test Artist"}],
                "releasegroups": [{"id": "rg-uuid", "title": "Test EP", "type": "EP"}]
            }]
        }]
    }
```

### Core assertions

- Return value is a `dict`.
- All expected keys are present (compare against a hardcoded key list).
- `acoustid_match` is always a bool (never None).
- `lookup_error` is absent on a successful lookup.
- `genres` and `tags` are lists (not None) when the MB lookup succeeds but returns
  no genres/tags (they should be `[]`, not `None`).

### Success path tests

- Full success (fingerprint → AcoustID match → MB recording → release label):
  assert all top-level fields are populated correctly.
- Success with no releases linked to recording: `mb_release_id`, `label`,
  `catalogue_number` all `None`; other MB fields populated.
- Success with `fetch_label=False`: `label` and `catalogue_number` are `None`;
  no second MB call made.
- Success with `mb_rate_limit=False`: no `time.sleep` called.

### No-match and partial failure tests

- AcoustID returns empty results: `acoustid_match = False`; all ID keys `None`;
  no `lookup_error`.
- AcoustID result has `recordings: []`: `acoustid_id` and `acoustid_score` set;
  `mb_recording_id = None`.
- MusicBrainz 404 (`ResponseError`): `mb_recording_id` stored; all MB metadata
  fields `None`; no `lookup_error`.
- Release lookup raises: `label = None`, `catalogue_number = None`; recording
  fields intact; no `lookup_error`.

### Failure path tests

- `NoBackendError` from fingerprint: `lookup_error` set; all keys `None`.
- `FingerprintGenerationError` from fingerprint: `lookup_error` set; all keys `None`.
- `WebServiceError` on first AcoustID call, succeeds on retry: full success result.
- `WebServiceError` on both AcoustID calls: `lookup_error` set; all keys `None`.
- Unexpected exception inside function body: outer try/except catches it; `lookup_error`
  set; dict returned (never raises).

### Rate limit test

- Mock `time.sleep` and assert it is called once per MusicBrainz call when
  `mb_rate_limit=True` and not called when `mb_rate_limit=False`.

---

## Open Questions

| # | Question | Blocks plan? | Interim decision |
|---|---|---|---|
| Q1 | AcoustID score threshold for a "trusted" match | No — deferred | Store raw `acoustid_score` always. Threshold for "needs manual review" is a Phase 2 calibration decision. |
| Q2 | Match rate on the real Crate library (estimated 30–60% no-match for techno/house) | No — deferred | Pipeline handles no-match gracefully. Validate with 50+ real tracks in Phase 2. |
| Q3 | Multiple recordings per AcoustID result — is `recordings[0]` always correct? | No — deferred | Take first recording; log when multiple exist. Investigate ambiguous cases in Phase 2. |
| Q4 | MusicBrainz rate limit in practice — does concurrent use at 2 workers cause 503s? | No — deferred | Do not add a lock pre-emptively. Add if 503s observed in Phase 2 testing. |
| Q5 | Release selection heuristic — when a recording has 15+ releases, which is "right"? | No — deferred | Earliest official release is a reasonable default. Validate on real popular tracks in Phase 2. |
| Q6 | Label/catalogue coverage for electronic music — how often is `label-info` populated? | No — deferred | Measure in Phase 2 with real tracks. Pipeline stores `None` gracefully when absent. |
| Q7 | ISRCs for electronic music — what fraction of DJ library tracks will have one? | No — deferred | Store `isrc` when present; `None` otherwise. Measure in Phase 2. |
| Q8 | `duration` unit difference (AcoustID: seconds integer; MB: milliseconds integer) | No — confirmed | AcoustID `duration` is in seconds; MusicBrainz `length` is in milliseconds. Confirmed from research doc. Pipeline converts MB ms → seconds when storing. |
| Q9 | fpcalc minimum file length for a valid fingerprint | No — deferred | Chromaprint can fingerprint files shorter than 120s. Very short clips (<10s) may produce low-confidence results. Test in Phase 2. |
| Q10 | Genre/tag coverage for techno and house in MusicBrainz | No — deferred | Store whatever is returned; `[]` if none. Interpret in Phase 2 after seeing real values. |

---

## Implementation Order

1. **Create `AcoustIDConfig` dataclass** in `backend/config.py` with all parameters
   from the Configuration section. Add default values. No logic — just the dataclass.

2. **Scaffold `acoustid.py`** with the function signature, the module-level
   `set_useragent` call, and the top-level try/except returning an empty error dict.
   Confirm the module imports without errors in WSL.

3. **Implement fingerprinting** — `acoustid.fingerprint_file` call, `NoBackendError`
   and `FingerprintGenerationError` handling. Return immediately on failure.

4. **Implement AcoustID lookup** — call, retry logic, empty-results handling, best
   result extraction, recordings check.

5. **Implement MusicBrainz recording lookup** — `get_recording_by_id`, rate limit
   sleep, `ResponseError` and `NetworkError` handling, field extraction,
   `_select_best_release` helper.

6. **Implement release lookup** — `get_release_by_id` with `inc=labels`, label and
   catalogue number extraction, guarded by `config.fetch_label`.

7. **Assemble the return dict** — all keys, no `lookup_error` on success.

8. **Write the test file** — mock all network calls, implement all test cases from
   the Test Plan above. Confirm all tests pass in WSL.
