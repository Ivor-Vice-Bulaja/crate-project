# iTunes Search API Research

Researched: 2026-04-11
Status: Complete for Phase 1 purposes.

---

## Sources

1. Apple Developer Documentation Archive — Overview
   https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html
   (Last updated by Apple: 2017-09-19)

2. Apple Developer Documentation Archive — Constructing Searches
   https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html

3. Apple Developer Documentation Archive — Lookup Examples
   https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/LookupExamples.html

4. Apple Developer Documentation Archive — Understanding Search Results
   https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/UnderstandingSearchResults.html

5. Live API responses fetched during research (2026-04-11):
   - `https://itunes.apple.com/search?term=aphex+twin&media=music&entity=song&limit=1`
   - `https://itunes.apple.com/search?term=daft+punk+around+the+world&media=music&entity=song&limit=1`
   - `https://itunes.apple.com/search?term=drumcode&media=music&entity=song&limit=5`
   - `https://itunes.apple.com/search?term=adam+beyer+drumcode&media=music&entity=song&limit=3`
   - `https://itunes.apple.com/search?term=kompakt&media=music&entity=song&limit=3`
   - `https://itunes.apple.com/search?term=burial+untrue&media=music&entity=song&limit=3`
   - `https://itunes.apple.com/search?term=bicep+glue&media=music&entity=song&limit=2`
   - `https://itunes.apple.com/lookup?id=1668862649` (Aphex Twin — Xtal)
   - `https://itunes.apple.com/lookup?id=696886431` (Daft Punk — Around the World)
   - `https://itunes.apple.com/lookup?id=909253&entity=album&limit=3` (artist + collections)
   - `https://itunes.apple.com/lookup?upc=724384603922` (UPC lookup test — returned empty)

6. PyPI — no relevant maintained Python library found (see Section 5).

---

## What the iTunes Search API Is

The iTunes Search API is a **free, public, unauthenticated REST API** maintained by Apple. It searches the iTunes Store and Apple Music catalogue across music, movies, podcasts, TV shows, apps, audiobooks, ebooks, and software. For music, it covers content available for purchase or streaming through Apple Music as of the date of the search.

**This is not the same as the Apple Music API.** The Apple Music API (documented at developer.apple.com) requires a developer token and MusicKit entitlement. The iTunes Search API is a legacy service, documented last in 2017, with no developer account required and no API key. It remains live and functional as of 2026.

Key characteristics:
- No authentication required — no API key, no OAuth, no developer account
- Searches the Apple Music / iTunes Store catalogue
- Returns JSON (or JSONP via `callback` parameter)
- Two distinct endpoints: search (keyword-based) and lookup (ID-based)
- Documentation was last updated 2017-09-19; the API has not been formally updated since

**Apple Music API vs iTunes Search API:**
| | iTunes Search API | Apple Music API |
|---|---|---|
| Auth required | No | Yes (developer token + MusicKit) |
| Rate limit | ~20 req/min (soft) | Higher, per developer terms |
| ISRC lookup | No | Yes |
| Label field | No | Yes |
| Catalogue number | No | Yes |
| Artwork sizes | Fixed (30/60/100px) | Templated (any size) |
| Documentation | Archived 2017 | Active |

---

## Search Endpoint Reference

### Base URL and endpoint

```
https://itunes.apple.com/search
```

Method: GET
Response format: JSON (UTF-8)

### Query parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `term` | string (URL-encoded) | Yes | — | Search query. Spaces encoded as `+`. Only letters, numbers, `.`, `-`, `_`, `*` are unencoded. |
| `country` | string (ISO 3166-1 alpha-2) | Yes (documented), No (in practice) | `US` | Determines which national storefront to search. Different storefronts have different catalogue coverage. |
| `media` | string (enum) | No | `all` | Media type to search. For music tracks use `music`. |
| `entity` | string (enum) | No | track entity for the media type | Sub-type of result within the media type. For music, use `song` for audio tracks. |
| `limit` | integer | No | `50` | Number of results to return. Range: 1–200. |
| `lang` | string (enum) | No | `en_us` | Language for results. Only two values: `en_us`, `ja_jp`. |
| `version` | integer | No | `2` | Response key version. Values: `1` or `2`. Use `2`. |
| `explicit` | string (enum) | No | `Yes` | Whether to include explicit content. Values: `Yes`, `No`. |
| `callback` | string | Yes (for cross-site) | — | JavaScript callback function name for JSONP. Not needed for server-side calls. |

**Note on `country`:** Although documented as required, the API accepts requests without it and defaults to the US storefront. Using `country=us` gives the broadest catalogue for most electronic music because the US store has the widest licensing coverage. Results differ by storefront — a release available in Germany may not appear in the US store.

### Entity values for `media=music`

| Entity | Returns |
|---|---|
| `song` | Individual audio tracks only |
| `musicTrack` | Audio tracks and music videos combined |
| `album` | Albums (collection-type results) |
| `musicArtist` | Artist-type results |
| `musicVideo` | Music video tracks only |
| `mix` | iTunes mixes |

**For Crate use:** `media=music&entity=song` is the correct combination to retrieve individual track metadata.

### Rate limits

The official documentation states: "approximately 20 calls per minute." This is described as subject to change. No formal SLA or enforcement mechanism is documented. Community reports (not confirmed from official sources) suggest the limit is enforced per IP address, not per application. Exceeding the rate limit returns an HTTP 403 response. Heavy usage should use the iTunes Enterprise Partner Feed (EPF) instead — EPF is a separate bulk data product not covered here.

**Practical guidance:** For background import enrichment at 5,000–20,000 tracks, 20 req/min means roughly 1,000 lookups per hour. With a ~30–60% match rate for a techno/house library, the API should complete enrichment for a 10,000-track library in 5–10 hours of background processing at the rate limit.

---

## Lookup Endpoint Reference

### Base URL and endpoint

```
https://itunes.apple.com/lookup
```

Method: GET
Response format: JSON (UTF-8)

### Supported ID types

| Parameter | Description |
|---|---|
| `id` | iTunes numeric ID for an artist, album, or track (the `trackId`, `artistId`, or `collectionId` from a search result) |
| `upc` | UPC or EAN barcode for an album |
| `isbn` | 13-digit ISBN (books only, not relevant for music) |
| `amgArtistId` | All Music Guide artist ID |
| `amgAlbumId` | All Music Guide album ID |
| `amgVideoId` | All Music Guide video ID |

**ISRC lookup: not supported.** There is no `isrc` parameter documented or observed. ISRC cannot be used as a lookup key in this API.

**UPC lookup:** Supported via `?upc=<value>`. A test with UPC `724384603922` returned zero results (`resultCount: 0, results: []`), suggesting that UPC coverage for older or niche electronic releases is incomplete.

### Additional lookup parameters

| Parameter | Description |
|---|---|
| `entity` | Expand a lookup — e.g., `?id=909253&entity=album` returns an artist result plus their albums |
| `limit` | Number of results per entity expansion |
| `sort` | Sort order; `recent` is a documented value |

### Example lookup URLs (from official documentation)

```
# Look up by iTunes artist ID
https://itunes.apple.com/lookup?id=909253

# Look up by UPC, including tracks
https://itunes.apple.com/lookup?upc=720642462928&entity=song

# Look up multiple AMG artist IDs
https://itunes.apple.com/lookup?amgArtistId=468749,5723

# Look up multiple AMG artist IDs, top 5 albums each
https://itunes.apple.com/lookup?amgArtistId=468749,5723&entity=album&limit=5

# Look up by AMG artist ID, 5 most recent songs
https://itunes.apple.com/lookup?amgArtistId=468749,5723&entity=song&limit=5&sort=recent
```

### Not-found response

When a lookup finds nothing, the API returns:
```json
{"resultCount": 0, "results": []}
```
This is not an HTTP error — it is a 200 OK with empty results. No HTTP 404 is returned for missing IDs.

---

## Field Inventory

### Track result object (wrapperType = "track", kind = "song")

The following fields were confirmed from live API responses during research. Sources: Aphex Twin "Xtal", Daft Punk "Around the World", Adam Beyer / Drumcode tracks, Kompakt tracks, Burial "Untrue" tracks, Bicep "Glue".

| JSON key | Type | Example value | Presence | Description | Notes for electronic music |
|---|---|---|---|---|---|
| `wrapperType` | string | `"track"` | Always | Type of result object. Always `"track"` for song results. | — |
| `kind` | string | `"song"` | Always | Sub-type. `"song"` for audio tracks; `"music-video"` for video. | — |
| `trackId` | integer | `1668862649` | Always | Apple's numeric ID for this specific track. | Stable for the lifetime of the catalogue entry. May change if Apple re-ingest a release. |
| `artistId` | integer | `39883194` | Always | Apple's numeric ID for the primary artist. | Stable across releases by the same artist. |
| `collectionId` | integer | `1668862636` | Always | Apple's numeric ID for the album/release. | — |
| `trackName` | string | `"Xtal"` | Always | Track title. | — |
| `artistName` | string | `"Aphex Twin"` | Always | Artist name as displayed in Apple Music. | May differ from MusicBrainz canonical name. |
| `collectionName` | string | `"Selected Ambient Works 85-92"` | Always | Album or release title. | — |
| `trackCensoredName` | string | `"Xtal"` | Always | Track title with explicit words starred out. Same as `trackName` when not explicit. | — |
| `collectionCensoredName` | string | `"Selected Ambient Works 85-92"` | Always | Album title with explicit words starred out. | — |
| `trackViewUrl` | string | `"https://music.apple.com/us/album/xtal/..."` | Always | Deep link to this track in Apple Music. | — |
| `artistViewUrl` | string | `"https://music.apple.com/us/artist/..."` | Always | Deep link to artist page in Apple Music. | — |
| `collectionViewUrl` | string | `"https://music.apple.com/us/album/..."` | Always | Deep link to album page in Apple Music. | — |
| `previewUrl` | string | `"https://audio-ssl.itunes.apple.com/..."` | Always (for tracks) | URL to a 30-second AAC preview clip. | Transient — these URLs expire. Do not cache. |
| `artworkUrl30` | string | `"https://is1-ssl.mzstatic.com/.../30x30bb.jpg"` | Always when artwork exists | Album artwork at 30×30px. | URL is a template — see artwork section below. |
| `artworkUrl60` | string | `"https://is1-ssl.mzstatic.com/.../60x60bb.jpg"` | Always when artwork exists | Album artwork at 60×60px. | URL is a template — see artwork section below. |
| `artworkUrl100` | string | `"https://is1-ssl.mzstatic.com/.../100x100bb.jpg"` | Always when artwork exists | Album artwork at 100×100px. | URL is a template — see artwork section below. |
| `releaseDate` | string (ISO 8601) | `"1992-02-12T12:00:00Z"` | Always | Release date in ISO 8601 format with time component. | Time component is always `T12:00:00Z` or `T08:00:00Z` — not meaningful. Date part is reliable at day precision for most releases. |
| `primaryGenreName` | string | `"Electronic"` | Always | Apple's genre classification. | Coarse (see Genre section). Observed values for electronic music: "Electronic", "Dance", "House", "Techno", "Trance". Not reliable for fine-grained genre distinction. |
| `trackTimeMillis` | integer | `293752` | Always (for tracks) | Track duration in **milliseconds**. | Useful for matching against file duration. |
| `discCount` | integer | `1` | Always | Total number of discs in the release. | — |
| `discNumber` | integer | `1` | Always | Disc number for this track. | — |
| `trackCount` | integer | `13` | Always | Total tracks on this disc. | — |
| `trackNumber` | integer | `1` | Always | Track position on this disc. | — |
| `country` | string | `"USA"` | Always | Storefront country for this result. Note: full country name, not ISO code. | Always matches the `country` query parameter (defaulting to USA). |
| `currency` | string | `"USD"` | Always | Currency for price fields. | Varies by storefront. |
| `collectionPrice` | float | `9.99` | Always | Album purchase price. `-1.00` if unavailable for individual purchase. | Not relevant for Crate. |
| `trackPrice` | float | `1.29` | Always | Track purchase price. `-1.00` if unavailable. | Not relevant for Crate. |
| `collectionExplicitness` | string | `"notExplicit"` | Always | Explicit content rating for the album. Values: `explicit`, `cleaned`, `notExplicit`. | — |
| `trackExplicitness` | string | `"notExplicit"` | Always | Explicit content rating for this track. Values: `explicit`, `cleaned`, `notExplicit`. | — |
| `isStreamable` | boolean | `true` | Always (observed) | Whether this track is available for streaming on Apple Music. | Not documented in official docs but present in all live responses. |
| `collectionArtistId` | integer | `4035426` | Sometimes | Artist ID for the collection artist when different from track artist. Present on Various Artists compilations. | — |
| `collectionArtistName` | string | `"Various Artists"` | Sometimes | Collection artist name when different from track artist. Present on compilations. | — |

**Fields confirmed absent from track results:**
- `isrc` — not present. Cannot be retrieved from the search or lookup endpoints.
- `label` — not present. Label name is not exposed.
- `catalogNumber` — not present.
- `bpm` — not present.
- `key` — not present.
- `amgArtistId` — sometimes present in artist-type results; not in track results.

### Collection result object (wrapperType = "collection")

When looking up an artist with `entity=album`, the response includes collection-type objects. Additional fields beyond track fields:

| JSON key | Type | Example value | Presence | Description |
|---|---|---|---|---|
| `collectionType` | string | `"Album"` | Always | Type of collection. |
| `copyright` | string | `"℗ 2001 Bubble Toes Music Publishing (ASCAP)"` | Always | Copyright string. Contains year and rights holder — sometimes the label name, sometimes the artist name. |
| `primaryGenreId` | integer | `21` | Sometimes | Numeric genre ID corresponding to `primaryGenreName`. |
| `amgArtistId` | integer | `468749` | Sometimes | All Music Guide artist ID. |

**Note on `copyright`:** This field contains the phonographic copyright string, which sometimes names the record label. It is not structured data — parsing the label name from it is unreliable. Example: `"℗ 2001 Bubble Toes Music Publishing (ASCAP)"` vs `"℗ 2022 Jack Johnson"`. Do not attempt to extract a label from this field programmatically.

### Artist result object (wrapperType = "artist")

| JSON key | Type | Example value |
|---|---|---|
| `artistType` | string | `"Artist"` |
| `artistName` | string | `"Jack Johnson"` |
| `artistLinkUrl` | string | deep link URL |
| `artistId` | integer | `909253` |
| `amgArtistId` | integer | `468749` |
| `primaryGenreName` | string | `"Rock"` |
| `primaryGenreId` | integer | `21` |

### Artwork URL templating

The `artworkUrl30`, `artworkUrl60`, and `artworkUrl100` fields follow a consistent URL pattern from mzstatic.com. The size specification at the end of the path (`/30x30bb.jpg`, `/60x60bb.jpg`, `/100x100bb.jpg`) can be substituted to request larger sizes. This is not officially documented in the iTunes Search API docs, but is consistent across all observed responses and is widely confirmed by the developer community.

Example substitution:
```
# From response:
https://is1-ssl.mzstatic.com/image/thumb/Music116/v4/5f/b3/e0/5fb3e08d.../cover.jpg/100x100bb.jpg

# Request 600x600:
https://is1-ssl.mzstatic.com/image/thumb/Music116/v4/5f/b3/e0/5fb3e08d.../cover.jpg/600x600bb.jpg
```

Common size values used by developers: `300x300`, `600x600`, `1200x1200`. Maximum available size is album-dependent — requesting a size larger than the source simply returns the original.

**This templating behaviour is not in the official documentation and could change without notice.** Treat artwork URLs as transient and not suitable for long-term caching.

---

## Python Integration

### PyPI library search

The PyPI web search interface returned an error page during research (JavaScript required to render results). Direct package URL lookups for `python-itunes`, `pyitunes`, and `itunes-py` all returned error pages from PyPI. No maintained Python library for the iTunes Search API could be confirmed.

**Assessment:** No well-maintained iTunes Search API Python library was found. This is consistent with general community knowledge — the API is simple enough (single GET request, JSON response) that a library adds little value. The raw HTTP approach is appropriate.

### Raw HTTP approach

The API requires only standard HTTP GET requests. Use the `requests` library (already a common dependency) or Python's built-in `urllib`.

**Search by artist + title:**
```python
import requests
import time

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
RATE_LIMIT_DELAY = 3.1  # seconds between requests to stay under ~20/min

def search_itunes_track(artist: str, title: str, country: str = "us") -> dict | None:
    """
    Search iTunes for a specific track by artist and title.
    Returns the best match result dict, or None if no results.
    """
    params = {
        "term": f"{artist} {title}",
        "media": "music",
        "entity": "song",
        "country": country,
        "limit": 5,
    }
    response = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])
    if not results:
        return None
    # Caller is responsible for selecting the best match from results
    return results[0]
```

**Lookup by iTunes trackId:**
```python
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"

def lookup_itunes_by_id(track_id: int) -> dict | None:
    params = {"id": track_id}
    response = requests.get(ITUNES_LOOKUP_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])
    return results[0] if results else None
```

**ISRC lookup:** Not supported by this API. Cannot implement.

**Rate limit handling:**
```python
import time

def rate_limited_search(artist: str, title: str) -> dict | None:
    result = search_itunes_track(artist, title)
    time.sleep(RATE_LIMIT_DELAY)  # 3.1s = ~19 req/min, under the limit
    return result
```

**HTTP error handling:**
- `403` — rate limit hit; back off and retry after 60 seconds
- `400` — malformed request (bad parameter); log and skip
- `503` / `5xx` — Apple service error; retry with exponential backoff
- `200` with `resultCount: 0` — no match; not an error

---

## Coverage for Electronic Music

All observations are from live API calls during research (2026-04-11). No published coverage statistics exist.

### Confirmed present in the catalogue

| Artist / Release | Confirmed |
|---|---|
| Aphex Twin — Selected Ambient Works 85-92 (R&S Records, 1992) | Yes — full album, trackId confirmed |
| Daft Punk — Homework (Virgin/Soma, 1997) | Yes — full album |
| Burial — Untrue (Hyperdub, 2007) | Yes — tracks present, genre "Electronic" |
| Bicep — Glue (Feel My Bicep, 2017) | Yes — present |
| Kompakt compilations (Kompakt label, Germany) | Yes — Kompakt Total 3 (2001), Kompakt Total 14 (2014) confirmed |
| Superpitcher on Kompakt | Yes |
| Jürgen Paape — "So weit wie noch nie" (Kompakt, 2001) | Yes |
| Adam Beyer / Drumcode-adjacent releases | Yes — tracks present, genres including "Techno", "Dance", "Electronic" |

### Likely absent or poorly covered

Based on observed response patterns and general knowledge of Apple Music licensing:

- **White label vinyl rips** — not present. Apple Music only carries commercially distributed digital releases.
- **Promos and unreleased tracks** — not present. No promo-only content observed.
- **Old vinyl from the 1990s–2000s not released digitally** — partially covered. Warp Records back catalogue is present (Aphex Twin 1992 confirmed). Small independent labels from the pre-digital era are unpredictable — coverage depends on whether the label has since licensed to Apple Music.
- **DJ edits, unofficial remixes** — not present. Apple Music requires rights clearance.
- **Tracks only released on Beatport without Apple Music licensing** — could not be confirmed; likely absent.

### Genre granularity

The `primaryGenreName` field is too coarse for the Crate use case. Observed values across electronic music queries:

| Observed genre | Assigned to |
|---|---|
| `"Electronic"` | Aphex Twin, Burial, Kompakt releases, Superpitcher |
| `"Dance"` | Daft Punk "Around the World", some Drumcode tracks, some Kompakt |
| `"House"` | Some Drumcode-named tracks, Bicep |
| `"Techno"` | Some Adam Beyer tracks |
| `"Trance"` | Some tracks with "Drumcode" in the title (genre misclassified) |

**Key finding:** Genre assignment is inconsistent. A Daft Punk techno-house track is labelled "Dance." Kompakt records labelled "Electronic" or "Dance" interchangeably. Trance results appeared for techno-adjacent searches. The `primaryGenreName` field **cannot be used reliably to distinguish techno from house** in a DJ library context.

### Coverage summary for Crate

| Content type | Expected match rate | Notes |
|---|---|---|
| Major-label electronic (Warp, Ninja Tune, Hyperdub, Kompakt) | High (~70–80%) | Confirmed for multiple releases |
| Drumcode, Afterlife, Rekids (mid-size techno labels) | Medium (~40–60%) | Partial coverage observed |
| Small white-label / promo-only releases | Very low (~0–10%) | These are not commercially distributed digitally |
| Old vinyl (pre-2000, not re-released digitally) | Low (~10–30%) | Depends on label's digital licensing history |

**Overall estimated match rate for a typical techno/house DJ library:** 30–50%. This is lower than a general pop library because of the high proportion of promo, white label, and vinyl-rip content in DJ collections.

---

## Comparison to Other Pipeline Sources

### iTunes Search API vs MusicBrainz

| Capability | iTunes Search API | MusicBrainz |
|---|---|---|
| Track title | Yes | Yes |
| Artist name | Yes | Yes (canonical + aliases) |
| Album title | Yes | Yes |
| Release date | Yes (day precision) | Yes (partial dates common) |
| Genre | Yes (coarse, 1 genre) | Yes (community tags, many genres) |
| Label name | No | Yes (separate release lookup) |
| Catalogue number | No | Yes (separate release lookup) |
| ISRC | No | Yes |
| Duration | Yes (milliseconds) | Yes (milliseconds, sometimes null) |
| Track number | Yes | Yes |
| Disc number | Yes | Yes |
| Artwork URL | Yes (direct, sized) | Via Cover Art Archive (separate service) |
| Artist country | No | Yes |
| Fingerprint match | No | Via AcoustID |
| Coverage for techno/house | ~30–50% match rate | ~30–60% match rate (similar) |

### Unique value of iTunes Search API for Crate

1. **Artwork URLs** — the most significant unique value-add. iTunes provides direct, CDN-hosted artwork URLs at multiple sizes. MusicBrainz/Cover Art Archive requires a separate lookup and the URLs are less reliable. iTunes artwork is consistently high quality for commercially released material.

2. **`trackId` as a stable cross-reference** — Apple's numeric track ID is stable and can be used for future lookups without re-running a search.

3. **Release date at day precision** — iTunes generally has the commercial release date, which can be more precise than MusicBrainz for releases where MB only has a year.

4. **No label or ISRC** — iTunes provides nothing that MusicBrainz does not for label/catalogue enrichment. MusicBrainz is strongly preferred for label data.

5. **Simpler to query** — no rate limit library required, no API key, no auth. Easier to integrate.

### Recommended role in the Crate pipeline

iTunes Search API is **optional enrichment** for:
- Artwork URL (primary use case — high confidence)
- Release date confirmation (secondary)
- `isStreamable` flag (if needed for set planning)

It should **not** be used as a primary source for:
- Artist/title (use mutagen tags + MusicBrainz)
- Label/catalogue number (use MusicBrainz + Discogs)
- Genre classification (too coarse; use Discogs community tags)
- ISRC (not available; use MusicBrainz)

---

## Failure Modes and Edge Cases

### Ambiguous search results

A `term` query for a common title ("Drumcode") returns tracks from multiple artists with no relation to the Drumcode label. The API has no label filter parameter. Disambiguation requires comparing `trackName` + `artistName` from the result against the known file tags.

**Mitigation:** Always search with both artist and title. Use `term=artistname+trackname`. Score results by comparing returned `artistName` and `trackName` against known values (fuzzy string match). Accept a result only above a similarity threshold.

### Multiple editions (remastered, extended, radio edit)

A search for "Aphex Twin Xtal" may return the 1992 original, a remaster, or a compilation version. The `collectionName` field distinguishes editions, but the API returns results by relevance, not date. The "correct" version for a DJ library match is the one with the closest duration (`trackTimeMillis` within ±5 seconds of the file's actual duration).

### Duration mismatches

DJ tracks are often longer than commercially released versions. A 12" original at 8:30 may be sold digitally as a 6:00 radio edit. `trackTimeMillis` is useful for version disambiguation — compare it against the file's actual duration from mutagen. Reject matches where the difference exceeds ±30 seconds (configurable threshold).

### Country parameter and catalogue breadth

`country=us` gives the broadest coverage for most electronic music because the US storefront has the widest licensing. However, some releases are available only in specific regional storefronts (e.g., a German-only release on Kompakt may be on `country=de` but not `country=us`). If a US lookup returns no results, retrying with `country=gb` or `country=de` may find the release.

### Special character encoding

Non-ASCII characters in artist names (e.g., "Jürgen Paape") are handled correctly by the API — the live response for Kompakt: Total 3 returned `"artistName":"Jürgen Paape"` with the umlaut intact. URL encoding of the query term should use standard `urllib.parse.urlencode` or the `requests` library's `params=` argument — both handle UTF-8 correctly.

### HTTP errors

| Status | Meaning | Action |
|---|---|---|
| `200` with empty `results` | No match found | Log and skip; not an error |
| `400` | Malformed request (bad parameter name or value) | Log the URL, fix the parameter, do not retry |
| `403` | Rate limit exceeded | Back off 60 seconds, then retry |
| `429` | Rate limit (alternative code — not documented but possible) | Same as 403 |
| `503` / `5xx` | Apple service error | Retry with exponential backoff (1s, 2s, 4s); skip after 3 failures |

### Lookup of expired or deleted IDs

If a previously stored `trackId` is looked up and the track has since been removed from Apple Music, the lookup returns `resultCount: 0`. The stored ID is then stale. This is unlikely to be a frequent issue for established releases but may occur for limited-time or regional content.

---

## Open Questions

The following could not be confirmed from documentation or the live API responses captured during this research session. Each should be tested in Phase 2 before relying on iTunes as a pipeline source.

1. **Artwork URL templating upper bound** — What is the maximum artwork resolution available? The pattern of substituting `600x600bb.jpg` or `1200x1200bb.jpg` is community-reported but not documented. Needs a live test comparing results at various sizes.

2. **Stability of `trackId` across re-ingests** — Apple sometimes re-ingests catalogue. Does a `trackId` stored today remain valid in 12 months? Could not be confirmed from documentation.

3. **`previewUrl` TTL** — How long do preview URLs remain valid? They appear to be signed or expiring CDN URLs. Do not store these — confirm by testing a stale URL.

4. **ISRC availability through Apple Music API** — The separate, authenticated Apple Music API reportedly exposes ISRC. If an Apple developer account is available in future, this could be added to the pipeline as a more capable replacement. Out of scope for Phase 1.

5. **Regional coverage difference** — Is there any release type (e.g., German electronic music) better covered by `country=de` than `country=us`? Needs systematic testing with known Kompakt/Tresor releases.

6. **Rate limit enforcement mechanism** — Is the ~20 req/min limit per IP, per account, or something else? The documentation says "approximately" and "subject to change." Needs testing under controlled conditions.

7. **Match rate on a real DJ library** — The 30–50% estimate is derived from qualitative observations during this research session. Needs validation against a real 1,000-track test set in Phase 2.

8. **`version=1` vs `version=2`** — What fields differ between the two response versions? The documentation mentions this parameter but does not describe the differences. Use `version=2` (the default) until there is a reason to investigate `version=1`.
