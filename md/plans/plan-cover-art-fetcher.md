# Implementation Plan: Cover Art Archive Fetcher

## Overview

`backend/importer/cover_art.py` takes MusicBrainz release and release-group MBIDs and
returns a flat dictionary containing a cover art URL and lookup metadata. It does not
download image bytes — it stores only the resolved redirect URL, which the frontend
fetches lazily at display time.

The module uses a two-step fallback: check the specific release first, then the release
group. An optional pre-check flag (`mb_has_front_art`) from the MusicBrainz pipeline
can skip the first CAA request entirely when the release is already known to have no art.

On any failure it returns a dict rather than raising, so the pipeline can always write
a partial result.

Full API reference: `md/research/research-cover-art-archive.md`.

---

## Function Interface

```python
def fetch_cover_art(
    release_mbid: str | None,
    release_group_mbid: str | None,
    config: CoverArtConfig,
    mb_has_front_art: bool | None = None,
) -> dict:
    ...
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `release_mbid` | `str \| None` | MusicBrainz release MBID (from AcoustID/MB pipeline) |
| `release_group_mbid` | `str \| None` | MusicBrainz release-group MBID (from AcoustID lookup or MB recording response) |
| `config` | `CoverArtConfig` | Dataclass of all tuneable settings (see Configuration) |
| `mb_has_front_art` | `bool \| None` | Pre-check flag from the `cover-art-archive.front` field in the MusicBrainz release response. `True` → definitely has art; `False` → skip release-level CAA call; `None` → unknown, attempt the call. |

### Return contract

| Situation | Return value |
|---|---|
| Art found at release level | Dict with `cover_art_url` set, `cover_art_source = "release"` |
| Art found at release-group level (release had no art) | Dict with `cover_art_url` set, `cover_art_source = "release_group"` |
| No art found at either level | Dict with `cover_art_url = None`, `cover_art_source = None` |
| Both MBIDs are `None` | Dict with `cover_art_url = None`, `cover_art_source = None` — no requests made |
| `mb_has_front_art = False`, no release-group MBID | Dict with `cover_art_url = None`, `cover_art_source = None` — no requests made |
| Network/unexpected error | Dict with `cover_art_url = None` plus `cover_art_error: str`; `cover_art_lookup_timestamp` always set |

A 404 from the CAA is **not** an error. It means no art is available. Do not set
`cover_art_error` on 404. Only set it on `requests.RequestException` or unexpected
exceptions.

Errors are **returned as structured data**, never raised. The pipeline never needs to
wrap this function in its own try/except.

---

## Lookup Strategy

The function follows this decision tree on each call:

```
1. If release_mbid is None AND release_group_mbid is None
       → return no-art dict immediately (no network calls)

2. Release-level lookup
   a. If mb_has_front_art is False
          → skip release-level CAA call (pre-check says no art)
   b. Else if release_mbid is not None
          → GET https://coverartarchive.org/release/{release_mbid}/front-{size}
            allow_redirects=False
          → If 307: store Location header URL; set source = "release"; return
          → If 404: continue to step 3
          → If other status or exception: log WARNING; continue to step 3

3. Release-group fallback
   a. If release_group_mbid is None
          → return no-art dict
   b. GET https://coverartarchive.org/release-group/{release_group_mbid}/front-{size}
      allow_redirects=False
      → If 307: store Location header URL; set source = "release_group"; return
      → If 404: return no-art dict
      → If other status or exception: log WARNING; return no-art dict with cover_art_error
```

**Why `allow_redirects=False`:** The CAA returns a 307 redirect to the actual image on
archive.org. Capturing the `Location` header gives us the stable `coverartarchive.org`
URL without downloading any image bytes.

**URL normalisation:** The CAA sometimes returns `http://` URLs in the Location header.
Always upgrade to `https://` before storing. Replace `http://coverartarchive.org` with
`https://coverartarchive.org`.

---

## Output Schema

All fields are always present in the returned dict. `cover_art_error` is only present
when a network or unexpected error occurred — it is not present on a clean no-match (404).

| Key | Python type | Description | Nullable? |
|---|---|---|---|
| `cover_art_url` | `str \| None` | Resolved `coverartarchive.org` HTTPS URL at the configured thumbnail size | None when no art found |
| `cover_art_source` | `str \| None` | `"release"` or `"release_group"` — which endpoint yielded the URL | None when no art found |
| `cover_art_lookup_timestamp` | `str` | ISO 8601 UTC timestamp of the lookup | Always set |
| `cover_art_error` | `str` | Error message — only present on network/unexpected failure, not on 404 | Only set on error |

---

## HTTP Behaviour Reference

The CAA uses redirects differently per endpoint. This module only uses the
`/front-{size}` endpoints, which always return 307 (not 200) on success.

| Endpoint | Success code | Failure code |
|---|---|---|
| `/release/{mbid}/front-{size}` | `307` (redirect to image) | `404` (no release or no art) |
| `/release-group/{mbid}/front-{size}` | `307` (redirect to image) | `404` (no group or no art) |

Do not attempt to parse a JSON body from these endpoints. The only data needed is
the `Location` header from the 307 response.

**400 Bad Request:** Indicates an invalid UUID was passed. Log at ERROR level (this is
a bug in the caller, not an expected case). Return no-art dict without `cover_art_error`.

**503 Service Unavailable:** Not currently enforced by the CAA, but retry with a single
1-second sleep once before giving up. Log at WARNING.

---

## Configuration

All tuneable values live in a `CoverArtConfig` dataclass in `backend/config.py`.

| Parameter | Controls | Default |
|---|---|---|
| `thumbnail_size` | Pixel width of the stored thumbnail URL (`250`, `500`, or `1200`) | `500` |
| `timeout` | `requests.get` timeout in seconds | `5` |
| `user_agent` | `User-Agent` header on all requests (CAA does not require one, but good practice) | `"CrateApp/0.1"` |

```python
@dataclass
class CoverArtConfig:
    thumbnail_size: int = 500
    timeout: int = 5
    user_agent: str = "CrateApp/0.1"
```

Add this dataclass to `backend/config.py` alongside `EssentiaConfig`, `AcoustIDConfig`,
and `DiscogsConfig`. No env vars needed — the CAA requires no authentication.

---

## Where MBIDs Come From

The pipeline (step 4 in CLAUDE.md) already fetches MusicBrainz data and produces:
- `release_mbid` — the best-matching release MBID from the MB recording lookup
- `release_group_mbid` — from `releasegroups[].id` in the AcoustID response, or from
  `releases[].release-group.id` in the MB recording response if `inc=release-groups`
  is added to that call

The `mb_has_front_art` flag comes from the `cover-art-archive.front` field in the MB
release response. This field is only present in direct release lookups
(`/ws/2/release/{mbid}?inc=labels`), which the AcoustID module already makes when
`config.fetch_label = True`. The pipeline should extract this flag from that response
and pass it to `fetch_cover_art`.

**If the pipeline cannot supply `mb_has_front_art`:** pass `None`. The function will
make the CAA request and handle a 404 gracefully. This costs one extra HTTP round-trip
but is always correct.

---

## Error Handling

| Failure mode | Strategy |
|---|---|
| Both MBIDs are `None` | Return no-art dict immediately; no log |
| `mb_has_front_art = False`, no release-group MBID | Return no-art dict immediately; no log |
| 404 from CAA at release level | No log; continue to release-group fallback |
| 404 from CAA at release-group level | No log; return no-art dict |
| 400 Bad Request from CAA | Log ERROR (caller bug); return no-art dict |
| `requests.RequestException` (timeout, connection error) | Log WARNING with MBID and exception; set `cover_art_error`; continue to release-group step if possible |
| Unexpected exception anywhere | Caught by outermost try/except; log ERROR; set `cover_art_error`; return no-art dict with timestamp |

The function must never raise. `cover_art_error` is only set on network or unexpected
failures, not on clean 404s.

---

## Integration with the Import Pipeline

Cover art lookup belongs between the MusicBrainz step and the Essentia step in the
pipeline. It runs over the network and is I/O-bound, so it can run concurrently with
Essentia in the same `ThreadPoolExecutor`.

```
Step 4 — MusicBrainz         → produces release_mbid, release_group_mbid, mb_has_front_art
Step 5a — Discogs            ┐ run concurrently
Step 5b — Cover art (CAA)    ┘
Step 6 — Essentia            ← also concurrent with 5a/5b
Step 7 — Derived scores
Step 8 — Write to DB
```

The function does not depend on Discogs output and Discogs does not depend on cover art
output. They are independent and can run in the same executor pool.

---

## Test Plan

Tests live in `backend/tests/test_importer/test_cover_art.py`.

Use `unittest.mock.patch("backend.importer.cover_art.requests.get")` to mock all HTTP
calls. No real network requests in tests.

### Mock response helper

```python
def mock_307(location: str):
    resp = unittest.mock.MagicMock()
    resp.status_code = 307
    resp.headers = {"Location": location}
    return resp

def mock_404():
    resp = unittest.mock.MagicMock()
    resp.status_code = 404
    return resp
```

### Test cases

| Test | Setup | Assertion |
|---|---|---|
| Release hit | `requests.get` → 307 with Location URL | `cover_art_url` is the Location URL (https); `cover_art_source = "release"` |
| Release miss, release-group hit | First call → 404; second call → 307 | `cover_art_url` set; `cover_art_source = "release_group"` |
| Both miss | Both calls → 404 | `cover_art_url = None`; `cover_art_source = None`; no `cover_art_error` |
| Pre-check skip (`mb_has_front_art=False`), release-group hit | Only one call made; → 307 | `cover_art_source = "release_group"`; `requests.get` called exactly once |
| Pre-check skip (`mb_has_front_art=False`), no release-group MBID | No calls made | `cover_art_url = None`; `requests.get` never called |
| Both MBIDs None | No calls made | `cover_art_url = None`; `requests.get` never called |
| URL normalisation | Location header returns `http://coverartarchive.org/...` | Stored URL starts with `https://` |
| Network error on release call | `requests.get` raises `requests.RequestException` | `cover_art_error` set; still attempts release-group fallback |
| Network error on both calls | Both raise `requests.RequestException` | `cover_art_error` set; `cover_art_url = None` |
| `cover_art_lookup_timestamp` always set | Any scenario | Field is a non-empty ISO 8601 string |

### Key assertions for all tests

- Return value is always a `dict`.
- All four schema keys are always present (`cover_art_url`, `cover_art_source`,
  `cover_art_lookup_timestamp`, and `cover_art_error` when applicable).
- The function never raises regardless of mock behaviour.

---

## Implementation Order

1. **Add `CoverArtConfig` dataclass** to `backend/config.py` with the three parameters
   from the Configuration section. No logic — just the dataclass.

2. **Create `cover_art.py`** with the function signature, module-level constant
   `_CAA_BASE = "https://coverartarchive.org"`, the outermost try/except, and a
   `_no_art_dict()` helper that returns a fully-null dict with the timestamp set.

3. **Implement the early-exit paths** — both MBIDs None; `mb_has_front_art=False` with
   no release-group MBID.

4. **Implement the release-level lookup** — build the URL, call `requests.get` with
   `allow_redirects=False`, handle 307 (extract Location, normalise to https, return),
   handle 404 (continue), handle other codes and exceptions (log, continue).

5. **Implement the release-group fallback** — same pattern as step 4 but using the
   release-group endpoint and setting `cover_art_source = "release_group"`.

6. **Assemble the return dict** — all schema keys, timestamp always set, `cover_art_error`
   only on network/unexpected failure.

7. **Write the test file** — mock helper, all test cases from the Test Plan. Confirm all
   tests pass without any real network calls.

8. **Wire up in the pipeline** — add the `fetch_cover_art` call to `pipeline.py` in the
   concurrent network phase alongside Discogs. Pass `release_mbid`, `release_group_mbid`,
   and `mb_has_front_art` from the MusicBrainz result dict.

---

## Open Questions

| # | Question | Blocks plan? | Interim decision |
|---|---|---|---|
| Q1 | Does the current AcoustID module surface `release_group_mbid` in its output dict? | No | The release-group MBID is available from the AcoustID response (`releasegroups[].id`). Confirm the key name when wiring up in pipeline.py. If absent, pass `release_group_mbid=None` and the release-group fallback is silently skipped. |
| Q2 | Does the current AcoustID module surface `mb_has_front_art` from the release lookup? | No | Pass `mb_has_front_art=None` until confirmed. The function handles `None` correctly — one extra CAA request per track at most. |
| Q3 | Should the stored URL be the `coverartarchive.org` redirect URL or the final `archive.org` URL? | No | Store the `coverartarchive.org` URL. The redirect layer handles MBID merges and storage reorganisation. The final `archive.org` URL is more fragile. |
| Q4 | Thumbnail size to store — 500px or 250px? | No | Default `500` in `CoverArtConfig`. 500px is sufficient for a DJ library UI; 250px is enough for a small thumbnail. Keep it configurable so it can be changed without touching the module. |
