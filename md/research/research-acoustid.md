# AcoustID + MusicBrainz Research

Researched 2026-04-03 from primary sources. All claims are traceable to the sources
listed below. Where information could not be confirmed from documentation, this is
stated explicitly.

---

## Sources

- AcoustID webservice API: https://acoustid.org/webservice
- Chromaprint library page: https://acoustid.org/chromaprint
- AcoustID database statistics: https://acoustid.org/stats
- pyacoustid source (acoustid.py): https://raw.githubusercontent.com/beetbox/pyacoustid/master/acoustid.py
- pyacoustid README: https://github.com/beetbox/pyacoustid
- MusicBrainz API documentation: https://musicbrainz.org/doc/MusicBrainz_API
- MusicBrainz API rate limiting: https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
- MusicBrainz data model: https://musicbrainz.org/doc/MusicBrainz_Database
- MusicBrainz recording definition: https://musicbrainz.org/doc/Recording
- MusicBrainz release definition: https://musicbrainz.org/doc/Release
- MusicBrainz release group definition: https://musicbrainz.org/doc/Release_Group
- MusicBrainz label definition: https://musicbrainz.org/doc/Label
- MusicBrainz catalogue number: https://musicbrainz.org/doc/Catalog_Number
- MusicBrainz API examples: https://musicbrainz.org/doc/MusicBrainz_API/Examples
- python-musicbrainzngs source: https://github.com/alastair/python-musicbrainzngs
- python-musicbrainzngs musicbrainz.py: https://raw.githubusercontent.com/alastair/python-musicbrainzngs/master/musicbrainzngs/musicbrainz.py
- Live MusicBrainz API responses: fetched directly during research session

---

## What AcoustID Is

### The AcoustID Service

AcoustID is a free, open-source audio fingerprint identification service. Given an audio
fingerprint generated from a local audio file, it returns a list of candidate MusicBrainz
recording IDs along with a confidence score. The service is maintained by Lukáš Lalinský,
hosted by AcoustID OÜ, and is explicitly licensed for non-commercial use only. Commercial
use requires separate registration at acoustid.biz.

AcoustID does not itself store full metadata. It is a fingerprint-to-MusicBrainz-recording
ID mapping layer. Once you have a recording ID from AcoustID, you query MusicBrainz
separately for the full metadata.

As of the research date, the AcoustID database contains:
- **74,126,781** unique AcoustIDs
- **91,438,851** fingerprints
- **21,055,209** linked recordings (MusicBrainz recording IDs)
- **1,043,866** active contributors

### Chromaprint

Chromaprint is the fingerprinting library that powers AcoustID. They are separate things:
Chromaprint generates the fingerprint locally on the client; AcoustID is the lookup service
that matches fingerprints against its database.

Chromaprint implements a custom algorithm for extracting acoustic fingerprints from raw
PCM audio data. It does **not** decode audio formats — the calling application is
responsible for decoding MP3, FLAC, M4A, etc. into raw PCM before passing data to
Chromaprint.

Chromaprint is written in C++ and provides a C API (`chromaprint.h`). The current release
is version 1.6.0. Precompiled binaries are available for Linux (x86_64, ARM64), macOS
(x86_64, ARM64, universal), and Windows (x86_64).

### fpcalc

`fpcalc` is a command-line tool bundled with Chromaprint that handles both audio decoding
(via FFmpeg/libavcodec) and fingerprint generation in a single step. It outputs JSON
containing the duration and fingerprint string. It is the recommended method for generating
fingerprints.

`fpcalc` is **not** bundled with pyacoustid. It must be installed separately (see
[Installation](#installation)). pyacoustid locates it either on `$PATH` or via the
`FPCALC` environment variable.

### pyacoustid

pyacoustid is a Python wrapper that provides:
1. Direct bindings to the Chromaprint C library (using ctypes)
2. A higher-level interface using `fpcalc` as a subprocess fallback
3. Functions to query the AcoustID web service

The library requires Python 3.10+. It depends on `audioread` for audio decoding (used
when calling Chromaprint directly, not when using fpcalc) and `requests` for HTTP.

pyacoustid's `fingerprint_file` function tries the Chromaprint C library first; if that
is not available, it falls back to running `fpcalc` as a subprocess. If neither is
available, it raises `NoBackendError`.

---

## AcoustID API Reference

### Base URL

```
https://api.acoustid.org/v2/
```

Requests can use GET or POST. POST with gzip-compressed body is preferred for large
fingerprints (set `Content-Encoding: gzip` header).

### Authentication

All requests require the `client` parameter — your application API key. API keys are
free and available at https://acoustid.org/api-key. A test key `FZ3bq_pP-A8` exists
but expires after a short period.

Fingerprint **submission** (not lookup) additionally requires a `user` parameter — a
user-specific API key obtained after signing in to acoustid.org.

### Rate Limits

**3 requests per second maximum.** This is enforced server-side. pyacoustid implements
client-side rate limiting internally: `REQUEST_INTERVAL = 0.33` seconds, enforced with
a thread-safe lock decorator on the lookup function.

The documentation does not distinguish between registered and anonymous API keys for the
rate limit — the 3 req/s limit applies to all users.

### Lookup Endpoint: `/lookup`

Accepts both fingerprint-based and track-ID-based lookups.

#### Request Parameters

| Parameter     | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `client`      | string  | Yes      | Application API key |
| `duration`    | integer | Yes (fingerprint lookup) | Audio duration in seconds |
| `fingerprint` | string  | Yes (fingerprint lookup) | Chromaprint fingerprint string |
| `trackid`     | string  | Yes (track ID lookup)   | AcoustID UUID for a known track |
| `meta`        | string  | No       | Space-separated list of metadata includes (see below) |
| `format`      | string  | No       | `json` (default), `jsonp`, or `xml` |
| `jsoncallback`| string  | No       | Callback name for JSONP |

#### `meta` Include Options

The `meta` parameter controls what metadata is returned alongside the AcoustID. Multiple
values are space-separated: `meta=recordings+releases+releasegroups`.

| Include value      | Effect |
|--------------------|--------|
| `recordings`       | Include full recording objects (title, artists, duration, releasegroups) |
| `recordingids`     | Include only the MusicBrainz recording UUIDs, no other metadata |
| `releases`         | Include release objects within each recording |
| `releaseids`       | Include only MusicBrainz release UUIDs |
| `releasegroups`    | Include release group objects within recordings |
| `releasegroupids`  | Include only release group UUIDs |
| `tracks`           | Include track-level data |
| `compress`         | Compress the response |
| `usermeta`         | Include user-submitted metadata |
| `sources`          | Include the number of sources that contributed to each result |

**For Crate**, the minimum useful call is `meta=recordings`. Adding `releasegroups` gives
album title and type without a second API call.

### Response Structure

All responses have a top-level `status` field. On success it is `"ok"`.

```json
{
  "status": "ok",
  "results": [
    {
      "id": "9ff43b6a-4f16-427c-93c2-92307ca505e0",
      "score": 1.0,
      "recordings": [
        {
          "id": "cd2e7c47-16f5-46c6-a37c-a1eb7bf599ff",
          "title": "Track Title",
          "duration": 639,
          "artists": [
            {
              "id": "uuid",
              "name": "Artist Name"
            }
          ],
          "releasegroups": [
            {
              "id": "uuid",
              "title": "Album Title",
              "type": "Album"
            }
          ]
        }
      ]
    }
  ]
}
```

#### Top-level Fields

| Field     | Type   | Always present | Description |
|-----------|--------|---------------|-------------|
| `status`  | string | Yes           | `"ok"` on success |
| `results` | array  | Yes           | Array of result objects; empty array `[]` if no match |

#### Result Object Fields

| Field        | Type   | Always present | Description |
|--------------|--------|---------------|-------------|
| `id`         | string | Yes           | AcoustID UUID — identifies this fingerprint in the AcoustID database |
| `score`      | float  | Yes           | Confidence score, range 0.0–1.0 |
| `recordings` | array  | Only if `meta=recordings` | Array of MusicBrainz recording objects linked to this AcoustID |
| `sources`    | integer| Only if `meta=sources` | Number of contributors who submitted this fingerprint |

#### Recording Object Fields (within `results[].recordings[]`)

| Field          | Type   | Always present | Description |
|----------------|--------|---------------|-------------|
| `id`           | string | Yes           | MusicBrainz recording UUID |
| `title`        | string | Sometimes     | Recording title; absent if not in MusicBrainz |
| `duration`     | integer| Sometimes     | Duration in seconds (median of linked track durations) |
| `artists`      | array  | Sometimes     | Array of artist credit objects |
| `releasegroups`| array  | Only if `meta=releasegroups` | Array of release group objects |
| `releases`     | array  | Only if `meta=releases` | Array of release objects |

#### Artist Object (within `recordings[].artists[]`)

| Field  | Type   | Always present | Description |
|--------|--------|---------------|-------------|
| `id`   | string | Yes           | MusicBrainz artist UUID |
| `name` | string | Yes           | Artist name as credited |

#### Release Group Object (within `recordings[].releasegroups[]`)

| Field    | Type   | Always present | Description |
|----------|--------|---------------|-------------|
| `id`     | string | Yes           | MusicBrainz release group UUID |
| `title`  | string | Sometimes     | Release group title |
| `type`   | string | Sometimes     | Primary type: `"Album"`, `"Single"`, `"EP"`, `"Broadcast"`, `"Other"` |

### Confidence Scoring

The `score` field is a float in the range **0.0 to 1.0**.

- `1.0` indicates an exact match between the submitted fingerprint and a stored fingerprint
- Lower scores indicate partial matches (fingerprint differs somewhat from stored data)
- `score` reflects fingerprint similarity, not metadata confidence

**The AcoustID documentation does not specify an official threshold above which a match
should be trusted.** Community convention (used by tools like beets) typically treats
scores ≥ 0.5 as plausible matches and scores ≥ 0.9 as strong matches, but these are
not documented thresholds.

### No-Match Response

When the fingerprint does not match anything in the database, the response is:

```json
{
  "status": "ok",
  "results": []
}
```

An empty `results` array is the canonical "no match" response. There is no distinct error
code for "not in database" vs "fingerprint didn't match" — both produce an empty array.

### Error Response Format

The API documentation does not exhaustively specify error codes. The `status` field is
`"ok"` on success. Failed requests (invalid API key, malformed parameters, rate limit
exceeded) return HTTP-level errors; the exact response body format for errors is not
documented in the official API documentation.

### Multiple Results

Multiple result objects in `results[]` can be returned, ordered by score descending.
Each result object has its own AcoustID UUID and its own list of linked recordings.
It is possible for one fingerprint to match multiple AcoustIDs, each linked to different
recordings. This occurs when the same audio has been submitted under different track
identities.

---

## pyacoustid Reference

Source: https://github.com/beetbox/pyacoustid (acoustid.py)

### Constants

| Constant           | Value    | Meaning |
|--------------------|----------|---------|
| `API_BASE_URL`     | `"http://api.acoustid.org/v2/"` | Base URL for all API calls |
| `DEFAULT_META`     | `["recordings"]` | Default `meta` parameter if none specified |
| `REQUEST_INTERVAL` | `0.33`   | Minimum seconds between API calls (enforces 3 req/s) |
| `MAX_AUDIO_LENGTH` | `120`    | Maximum seconds of audio passed to fingerprinter |

### Functions

#### `fingerprint_file(path, maxlength=MAX_AUDIO_LENGTH, force_fpcalc=False)`

Generates a fingerprint from a local audio file.

- **`path`**: Path to the audio file (any format supported by audioread/fpcalc)
- **`maxlength`**: Maximum seconds of audio to fingerprint (default: 120)
- **`force_fpcalc`**: If `True`, always uses fpcalc even if Chromaprint C library is available

**Returns**: `(duration, fingerprint)` tuple
- `duration`: float, audio duration in seconds
- `fingerprint`: string, the Chromaprint fingerprint

**Strategy**: Tries Chromaprint C library first (via ctypes). Falls back to running
`fpcalc` as a subprocess if the library is not found. Raises `NoBackendError` if
neither is available.

**Raises**:
- `NoBackendError` — Chromaprint library and fpcalc both unavailable
- `FingerprintGenerationError` — Audio decoding or fingerprinting failed

#### `lookup(apikey, fingerprint, duration, meta=DEFAULT_META, timeout=None)`

Queries the AcoustID web service with a fingerprint.

- **`apikey`**: Your AcoustID application API key
- **`fingerprint`**: String from `fingerprint_file`
- **`duration`**: Integer or float, audio duration in seconds
- **`meta`**: List of strings for `meta` parameter (default: `["recordings"]`)
- **`timeout`**: Optional request timeout in seconds (passed to `requests`)

**Returns**: Parsed JSON response as a Python dict (the full `{"status": ..., "results": [...]}` structure).

**Raises**:
- `WebServiceError` — HTTP request failed or non-OK response

Rate-limited internally to 3 requests/second via a thread-safe decorator.

#### `parse_lookup_result(data)`

Parses the raw lookup response dict into a simpler iterator.

- **`data`**: The dict returned by `lookup`

**Yields**: `(score, recording_id, title, artist_name)` tuples
- `score`: float 0.0–1.0
- `recording_id`: MusicBrainz recording UUID string, or `None` if no recordings
- `title`: recording title string, or `None`
- `artist_name`: combined artist name string (join phrases applied), or `None`

**Note**: This function discards most of the response. It does not yield release,
release group, label, or year information. For Crate, use `lookup` directly and
parse the full response rather than relying on `parse_lookup_result`.

#### `match(apikey, path, meta=DEFAULT_META, parse=True, timeout=None)`

Convenience wrapper combining `fingerprint_file` and `lookup`.

- **`apikey`**: AcoustID API key
- **`path`**: Path to audio file
- **`meta`**: `meta` parameter for the lookup
- **`parse`**: If `True` (default), yields `(score, recording_id, title, artist)` tuples via `parse_lookup_result`. If `False`, returns raw response dict.
- **`timeout`**: Request timeout

**Returns**: If `parse=True`, yields `(score, recording_id, title, artist)` tuples.
If `parse=False`, returns raw response dict from `lookup`.

For Crate, call with `parse=False` to get the full response.

#### `fingerprint(samplerate, channels, pcmiter)`

Low-level function. Generates a fingerprint from raw PCM data.

- **`samplerate`**: Sample rate in Hz (integer)
- **`channels`**: Number of channels (integer)
- **`pcmiter`**: Iterator or iterable of PCM data (bytearray or buffer objects)

**Returns**: fingerprint string

Requires the Chromaprint C library. Does not fall back to fpcalc.

#### `compare_fingerprints(a, b)`

Compares two fingerprint strings. Uses XOR bit-error calculation with alignment offset
matching. Constants: `MAX_BIT_ERROR = 2`, `MAX_ALIGN_OFFSET = 120`.

**Returns**: similarity float (range not documented in source; higher = more similar)

#### `submit(apikey, userkey, data)`

Submits one or more fingerprints to AcoustID.

- **`data`**: dict or list of dicts with required keys `fingerprint` and `duration`,
  plus optional keys `mbid`, `track`, `artist`, `album`, `albumartist`, `year`, `trackno`, `discno`

**Returns**: raw response dict with submission IDs

#### `get_submission_status(apikey, submission_id)`

Checks status of a previously submitted fingerprint.

**Returns**: raw response dict; submission `status` is `"pending"` or `"imported"`

#### `set_base_url(url)`

Configures a custom AcoustID server URL. Used for testing or self-hosted instances.

### Exception Classes

| Exception                   | Parent                       | Raised when |
|-----------------------------|------------------------------|-------------|
| `AcoustidError`             | `Exception`                  | Base class for all pyacoustid errors |
| `FingerprintGenerationError`| `AcoustidError`              | Audio decoding or fingerprinting failed |
| `NoBackendError`            | `FingerprintGenerationError` | Neither Chromaprint library nor fpcalc is available |
| `FingerprintSubmissionError`| `AcoustidError`              | Required submission data is missing |
| `WebServiceError`           | `AcoustidError`              | HTTP request failed or API returned an error; has optional `.error_code` attribute |

---

## MusicBrainz Data Model

### Precise Entity Definitions

#### Recording

A recording is a distinct captured audio performance or mix. It exists at a stage in the
production process after any editing or mixing but before final mastering.

Key properties:
- `id` (MBID): UUID
- `title`: string
- `length`: integer, milliseconds — calculated as median of all linked track durations (or manually entered)
- `artist-credit`: array of credited artists with join phrases
- `isrcs`: array of ISRC strings
- `disambiguation`: string
- `first-release-date`: string (YYYY-MM-DD), earliest release date of any release containing this recording
- `video`: boolean

**A recording is not a track.** A track is a position on a medium (disc side, CD, etc.)
within a specific release. One recording can be linked to multiple tracks across many
releases. For example, the same studio recording appearing on an original single and a
compilation is one recording linked to two tracks.

**A recording is not a release.** The release is the product (CD, vinyl, digital download);
the recording is the audio content.

#### Release

A release is a specific, unique issuing of a product containing audio. Different pressings
of the same album in different countries or on different formats are separate releases.

Key properties:
- `id` (MBID): UUID
- `title`: string
- `artist-credit`: array
- `date`: string (YYYY, YYYY-MM, or YYYY-MM-DD)
- `country`: ISO 3166-1 alpha-2 code
- `status`: `"Official"`, `"Promotion"`, `"Bootleg"`, `"Pseudo-Release"`, `"Withdrawn"`, `"Cancelled"`
- `barcode`: string (UPC/EAN), can be null
- `label-info`: array of `{catalog-number, label}` objects — note field name is `catalog-number` (American spelling)
- `packaging`: string or null
- `text-representation`: `{language, script}`
- `quality`: `"normal"`, `"low"`, `"high"`
- `disambiguation`: string
- `release-events`: array of `{date, area}` objects — all regional release dates
- `mediums`: array of medium objects (when `inc=media` or `inc=recordings`)

#### Track (within a Release)

A track is a position on a medium. It is not directly queryable — it only appears when
you request a release with `inc=recordings`.

Key properties:
- `id` (MBID): UUID (track-level MBID, distinct from recording MBID)
- `title`: string (can differ from recording title — e.g. bonus track renaming)
- `number`: string (track number as printed)
- `position`: integer (1-based position within the medium)
- `length`: integer, milliseconds
- `recording`: the recording object linked to this track position

#### Release Group

A release group is the conceptual album or work that groups multiple releases. Every
release belongs to exactly one release group, created automatically.

Key properties:
- `id` (MBID): UUID
- `title`: string
- `artist-credit`: array
- `primary-type`: `"Album"`, `"Single"`, `"EP"`, `"Broadcast"`, `"Other"`
- `secondary-types`: array of strings — `"Compilation"`, `"Remix"`, `"DJ-mix"`, `"Live"`, etc.
- `disambiguation`: string
- `first-release-date`: string

#### Label

A label represents an imprint, record company, or music group. The catalogue number lives
on the **release**, not the label entity itself.

Key label properties: `id`, `name`, `sort-name`, `type` (Imprint/Original Production/Bootleg Production/Reissue Production/Distribution/Holding/Rights Society), `label-code`, `area`, `begin-date`, `end-date`

---

## MusicBrainz API Reference

### Base URL

```
https://musicbrainz.org/ws/2/
```

### Response Format

Default is XML. For JSON, either add `fmt=json` to the query string or set
`Accept: application/json` header. The `fmt=json` query parameter takes precedence.

### Rate Limits

**1 request per second maximum** (averaged). This is strictly enforced per IP address.

If exceeded: HTTP 503 Service Unavailable. The documentation states: "we decline 100%
of them, until the rate drops below the limit." Recovery requires waiting for the rate
to drop below 1 req/s on average.

**Global server limit**: 300 req/s across all users.

Some known user-agents (headphones, beets, Python-musicbrainz/0.7.3) are throttled to
50 req/s regardless of the per-IP limit. This is a server-side allowance for known tools,
not a guarantee.

### User-Agent Requirement

A meaningful User-Agent header is **mandatory**. Applications using blank user-agents,
`Java`, `Python-urllib`, or other generic clients will be throttled.

Required format (either of):
```
AppName/version ( contact-url )
AppName/version ( contact-email )
```

Example for Crate:
```
CrateApp/0.1 ( your@email.com )
```

This must be set before making any requests. In musicbrainzngs, this is done via
`musicbrainzngs.set_useragent("CrateApp", "0.1", "your@email.com")`.

### Recording Lookup Endpoint

```
GET https://musicbrainz.org/ws/2/recording/{MBID}?inc={INCLUDES}&fmt=json
```

Example:
```
https://musicbrainz.org/ws/2/recording/b9ad642e-b012-41c7-b72a-42cf4911f9ff?inc=artist-credits+isrcs+releases&fmt=json
```

#### inc Parameters for Recording Lookup

| `inc` value         | Effect |
|---------------------|--------|
| `artist-credits`    | Full artist credit objects including `joinphrase` and nested `artist` objects with sort-name, country, type |
| `releases`          | All releases that contain this recording |
| `isrcs`             | ISRC codes associated with this recording |
| `tags`              | Community-contributed tags (text labels) |
| `user-tags`         | Authenticated user's own tags (requires auth) |
| `genres`            | Genre classifications |
| `user-genres`       | Authenticated user's genres (requires auth) |
| `ratings`           | Community ratings |
| `user-ratings`      | Authenticated user's ratings (requires auth) |
| `aliases`           | Alternative names for the recording |
| `annotation`        | Editorial annotation text |
| `work-level-rels`   | Relationships to works (compositions) |
| `artist-rels`       | Relationships to artists (e.g. producer, remixer) |
| `release-rels`      | Relationships to releases |
| `url-rels`          | Relationships to URLs (e.g. streaming links) |
| `discids`           | Disc IDs (requires `releases` also included) |
| `media`             | Medium format information for releases |

Multiple includes are joined with `+`: `inc=artist-credits+isrcs+releases+tags+genres`

**To obtain label and catalogue number**, you cannot get them from a recording lookup
directly. The `releases` include on a recording gives bare release objects without
label-info. You need a separate release lookup:
```
GET /ws/2/release/{RELEASE_MBID}?inc=labels&fmt=json
```

### Full Recording JSON Response Structure

Confirmed from live API response. Recording with `inc=artist-credits+isrcs+releases`:

```json
{
  "id": "b9ad642e-b012-41c7-b72a-42cf4911f9ff",
  "title": "LAST ANGEL",
  "length": 230240,
  "disambiguation": "",
  "video": false,
  "first-release-date": "2007-11-07",
  "isrcs": ["JPB600760301"],
  "artist-credit": [
    {
      "name": "倖田來未",
      "joinphrase": " feat. ",
      "artist": {
        "id": "455641ea-fff4-49f6-8fb4-49f961d8f1ac",
        "name": "倖田來未",
        "sort-name": "Koda, Kumi",
        "type": "Person",
        "type-id": "b6e035f4-3ce9-331c-97df-83397230b0df",
        "country": "JP",
        "disambiguation": ""
      }
    }
  ],
  "releases": [
    {
      "id": "9c7a7669-b43a-3323-906b-c3f0bedc10c9",
      "title": "LAST ANGEL",
      "status": "Official",
      "status-id": "4e304316-386d-3409-af2e-78857eec5cfe",
      "date": "2007-11-07",
      "country": "JP",
      "barcode": "4988064457663",
      "packaging": null,
      "packaging-id": null,
      "quality": "normal",
      "disambiguation": "",
      "text-representation": {
        "language": "jpn",
        "script": "Jpan"
      },
      "release-events": [
        {
          "date": "2007-11-07",
          "area": {
            "id": "2db42837-c832-3c27-b4a3-08198f75693c",
            "name": "Japan",
            "sort-name": "Japan",
            "iso-3166-1-codes": ["JP"],
            "type": null,
            "type-id": null,
            "disambiguation": ""
          }
        }
      ],
      "artist-credit": [ ... ]
    }
  ]
}
```

#### Recording-level Field Reference

| Field                | Type    | Always present | Description |
|----------------------|---------|---------------|-------------|
| `id`                 | string  | Yes           | MusicBrainz recording UUID |
| `title`              | string  | Yes           | Recording title |
| `length`             | integer | Sometimes     | Duration in **milliseconds**; null if unknown |
| `disambiguation`     | string  | Yes           | Usually `""`; populated to distinguish identical-title recordings |
| `video`              | boolean | Yes           | `true` if this is a video recording |
| `first-release-date` | string  | Sometimes     | Earliest release date, format `YYYY-MM-DD`, `YYYY-MM`, or `YYYY`; absent if no releases linked |
| `isrcs`              | array   | Only if `inc=isrcs` | Array of ISRC strings; can be empty `[]` |
| `artist-credit`      | array   | Only if `inc=artist-credits` | Array of artist credit objects |
| `releases`           | array   | Only if `inc=releases` | Array of release objects (bare, no label-info) |
| `tags`               | array   | Only if `inc=tags` | Array of `{name, count}` objects |
| `genres`             | array   | Only if `inc=genres` | Array of `{id, name, count}` objects |

#### Release Object Fields (when embedded in recording response)

| Field                  | Type    | Always present | Description |
|------------------------|---------|---------------|-------------|
| `id`                   | string  | Yes           | Release MBID |
| `title`                | string  | Yes           | Release title |
| `status`               | string  | Sometimes     | `"Official"`, `"Promotion"`, `"Bootleg"`, `"Pseudo-Release"` |
| `status-id`            | string  | Sometimes     | UUID for the status value |
| `date`                 | string  | Sometimes     | Release date; format varies (YYYY, YYYY-MM, YYYY-MM-DD); absent if unknown |
| `country`              | string  | Sometimes     | ISO 3166-1 code; null if worldwide/unknown |
| `barcode`              | string  | Sometimes     | UPC/EAN barcode; null if absent |
| `packaging`            | string  | Sometimes     | Packaging type string; null if unknown |
| `packaging-id`         | string  | Sometimes     | UUID for packaging type; null if unknown |
| `quality`              | string  | Yes           | Data quality: `"normal"`, `"low"`, `"high"` |
| `disambiguation`       | string  | Yes           | Usually `""`; differentiates identical-title releases |
| `text-representation`  | object  | Sometimes     | `{language, script}` — ISO 639-3 language code and ISO 15924 script code |
| `release-events`       | array   | Sometimes     | All regional release dates as `{date, area}` objects |
| `artist-credit`        | array   | Only if `inc=artist-credits` | Full artist credits on this release |

**Note**: `label-info` and `catalog-number` are NOT present in releases embedded within
a recording lookup. To get them, do a separate release lookup with `inc=labels`.

#### Release Lookup with Labels

```
GET /ws/2/release/{RELEASE_MBID}?inc=labels&fmt=json
```

Adds `label-info` to the release object:

```json
"label-info": [
  {
    "catalog-number": "RZCD-45766",
    "label": {
      "id": "72a46579-e9a0-405a-8ee1-e6e6b63b8212",
      "name": "rhythm zone",
      "sort-name": "rhythm zone",
      "type": "Imprint",
      "type-id": "b6285b2a-3514-3d43-80df-fcf528824ded",
      "label-code": null,
      "disambiguation": ""
    }
  }
]
```

Note the American spelling: `catalog-number` (not `catalogue-number`).

### Release Statuses

`"Official"` — Normal commercial release
`"Promotion"` — Promotional release not for sale
`"Bootleg"` — Unofficial/unauthorised release
`"Pseudo-Release"` — Unofficial translation/transliteration
`"Withdrawn"` — Release pulled from sale
`"Cancelled"` — Announced but not released

### Release Group Primary Types

`"Album"`, `"Single"`, `"EP"`, `"Broadcast"`, `"Other"`

### Release Group Secondary Types

`"Compilation"`, `"Soundtrack"`, `"Spokenword"`, `"Interview"`, `"Audiobook"`,
`"Audio drama"`, `"Live"`, `"Remix"`, `"DJ-mix"`, `"Mixtape/Street"`, `"Demo"`,
`"Field recording"`

---

## musicbrainzngs Reference

Source: https://github.com/alastair/python-musicbrainzngs (musicbrainz.py)

### Setup

```python
import musicbrainzngs
musicbrainzngs.set_useragent("CrateApp", "0.1", "your@email.com")
```

`set_useragent` is **mandatory** before any API call. Without it, requests use a generic
user-agent that will be throttled server-side.

### `get_recording_by_id`

```python
result = musicbrainzngs.get_recording_by_id(
    id,                          # MusicBrainz recording UUID string
    includes=[],                 # list of inc parameter strings
    release_status=[],           # filter releases by status
    release_type=[]              # filter releases by type
)
```

**Returns**: `{"recording": { ... }}` — a dict with a single `"recording"` key containing
the recording object. Access data via `result["recording"]`.

**Valid `includes` values for recordings**:

```python
[
    "artists",           # artist objects (simpler than artist-credits)
    "releases",          # linked releases
    "discids",           # disc IDs (use with releases)
    "media",             # medium format info
    "artist-credits",    # full artist credit objects with joinphrase
    "isrcs",             # ISRC codes
    "work-level-rels",   # relationships to musical works
    "annotation",        # annotation text
    "aliases",           # alternative names
    "tags",              # community tags
    "user-tags",         # user's tags (requires auth)
    "ratings",           # community ratings
    "user-ratings",      # user's ratings (requires auth)
    "genres",            # genre classifications
    "user-genres",       # user's genres
    # Relationship includes:
    "area-rels", "artist-rels", "event-rels", "instrument-rels",
    "label-rels", "place-rels", "recording-rels", "release-rels",
    "release-group-rels", "series-rels", "url-rels", "work-rels"
]
```

### Other Recording Functions

```python
# Search by text
musicbrainzngs.search_recordings(query='', limit=None, offset=None, strict=False, **fields)
# Returns: {"recording-list": [...], "recording-count": N}

# Browse recordings linked to an artist or release
musicbrainzngs.browse_recordings(artist=None, release=None, includes=[], limit=None, offset=None)

# Look up by ISRC
musicbrainzngs.get_recordings_by_isrc(isrc, includes=[], release_status=[], release_type=[])
# Returns: {"isrc": {"recording-list": [...]}}
```

### Release Lookup

```python
result = musicbrainzngs.get_release_by_id(
    id,
    includes=["labels", "recordings", "artist-credits", "release-groups"]
)
# Returns: {"release": { ... }}
```

### Exception Classes

| Exception               | Parent             | Raised when |
|-------------------------|--------------------|-------------|
| `MusicBrainzError`      | `Exception`        | Base class |
| `UsageError`            | `MusicBrainzError` | Misuse of the module API |
| `InvalidSearchFieldError`| `UsageError`      | Invalid search field name |
| `InvalidIncludeError`   | `UsageError`       | Invalid include parameter |
| `WebServiceError`       | `MusicBrainzError` | API request failed |
| `NetworkError`          | `WebServiceError`  | Cannot communicate with server |
| `ResponseError`         | `WebServiceError`  | Bad response from server (e.g. 404, 503) |
| `AuthenticationError`   | `WebServiceError`  | HTTP 401 response |

**Not-found handling**: A 404 response from MusicBrainz raises `ResponseError`. Check
`except musicbrainzngs.ResponseError`.

### Maintenance Status

The library has 296 stars, 111 forks, 564 commits, 8 releases. It is actively maintained
as of the research date. Python version support is not specified in the README; the library
functions with Python 3.x. License: Simplified BSD.

---

## Field Inventory

Complete inventory of every field returned by both APIs, with presence indicators and
quality notes.

### Key

- **Always**: Present in every response of this type
- **Sometimes**: Present when the data exists in the database
- **Conditional**: Only present when specific `meta`/`inc` parameters are set
- **Never**: Not returned by this API

---

### AcoustID Lookup Response — All Fields

| JSON Path | Type | Presence | Description | Quality Notes |
|-----------|------|----------|-------------|---------------|
| `.status` | string | Always | `"ok"` on success | — |
| `.results` | array | Always | Result objects; `[]` if no match | — |
| `.results[].id` | string (UUID) | Always | AcoustID fingerprint identifier | Stable identifier |
| `.results[].score` | float | Always | Match confidence 0.0–1.0 | No official threshold documented |
| `.results[].recordings` | array | Conditional (`meta=recordings`) | MusicBrainz recordings linked to this fingerprint | Can be empty `[]` if fingerprint not linked to any recording |
| `.results[].recordings[].id` | string (UUID) | Always (within recordings) | MusicBrainz recording UUID | Use this for MusicBrainz lookup |
| `.results[].recordings[].title` | string | Sometimes | Recording title | Absent if not populated in MB |
| `.results[].recordings[].duration` | integer | Sometimes | Duration in **seconds** (integer, not ms) | Absent if no tracks linked |
| `.results[].recordings[].artists` | array | Sometimes | Artist credits | Absent if not populated |
| `.results[].recordings[].artists[].id` | string (UUID) | Always (within artists) | MusicBrainz artist UUID | — |
| `.results[].recordings[].artists[].name` | string | Always (within artists) | Artist name | — |
| `.results[].recordings[].releasegroups` | array | Conditional (`meta=releasegroups`) | Release groups | — |
| `.results[].recordings[].releasegroups[].id` | string (UUID) | Always (within releasegroups) | Release group UUID | — |
| `.results[].recordings[].releasegroups[].title` | string | Sometimes | Album/release group title | — |
| `.results[].recordings[].releasegroups[].type` | string | Sometimes | `"Album"`, `"Single"`, etc. | — |
| `.results[].sources` | integer | Conditional (`meta=sources`) | Contributor count for this fingerprint | Higher = more reliable |

**AcoustID returns no label, catalogue number, year, genre, ISRC, or key/BPM data.
All such data must come from MusicBrainz.**

---

### MusicBrainz Recording Lookup — All Fields

With `inc=artist-credits+isrcs+releases+tags+genres`. Confirmed from live API responses.

#### Recording Object

| JSON Path | Type | Presence | Description | Quality Notes |
|-----------|------|----------|-------------|---------------|
| `.id` | string (UUID) | Always | MusicBrainz recording UUID | Stable permanent identifier |
| `.title` | string | Always | Recording title | Generally reliable |
| `.length` | integer | Sometimes | Duration in **milliseconds** | Null if no tracks linked; can differ from AcoustID's `duration` |
| `.disambiguation` | string | Always | `""` unless needed to distinguish | Usually empty |
| `.video` | boolean | Always | Whether this is a video recording | Reliable |
| `.first-release-date` | string | Sometimes | Earliest known release date; `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` | Present when at least one release is linked; year precision varies |
| `.isrcs` | array of strings | Conditional (`inc=isrcs`) | ISRC codes; can be `[]` | Incomplete for electronic music; white labels and promos often have none |
| `.artist-credit` | array | Conditional (`inc=artist-credits`) | Full artist credits with join phrases | See below |
| `.artist-credit[].name` | string | Always (within artist-credit) | Name as credited on this recording | May differ from canonical artist name |
| `.artist-credit[].joinphrase` | string | Always (within artist-credit) | Text joining this credit to the next (e.g. `" feat. "`, `" & "`, `""`) | — |
| `.artist-credit[].artist` | object | Always (within artist-credit) | Full artist object | See below |
| `.artist-credit[].artist.id` | string (UUID) | Always | Artist MBID | Stable |
| `.artist-credit[].artist.name` | string | Always | Canonical artist name | — |
| `.artist-credit[].artist.sort-name` | string | Always | Sort-order name (e.g. `"Surgeon"` → `"Surgeon"`) | — |
| `.artist-credit[].artist.type` | string | Sometimes | `"Person"`, `"Group"`, `"Orchestra"`, `"Choir"`, `"Character"`, `"Other"` | — |
| `.artist-credit[].artist.type-id` | string (UUID) | Sometimes | UUID for the type value | — |
| `.artist-credit[].artist.country` | string | Sometimes | ISO 3166-1 code; null if unknown | Often missing for older entries |
| `.artist-credit[].artist.disambiguation` | string | Always | Usually `""` | — |
| `.releases` | array | Conditional (`inc=releases`) | All releases containing this recording | Can be very large (20+ releases for a popular track); see notes |
| `.releases[].id` | string (UUID) | Always (within releases) | Release MBID | — |
| `.releases[].title` | string | Always (within releases) | Release title | — |
| `.releases[].status` | string | Sometimes | `"Official"`, `"Promotion"`, `"Bootleg"`, `"Pseudo-Release"` | Sometimes absent for older entries |
| `.releases[].date` | string | Sometimes | Release date; partial dates possible | Often only year-level precision for older releases |
| `.releases[].country` | string | Sometimes | Release country ISO code; null for worldwide | — |
| `.releases[].barcode` | string | Sometimes | UPC/EAN barcode; null if absent | Frequently missing |
| `.releases[].quality` | string | Always (within releases) | `"normal"`, `"low"`, `"high"` | — |
| `.releases[].disambiguation` | string | Always (within releases) | Usually `""` | — |
| `.releases[].release-events` | array | Sometimes | All regional release dates | — |
| `.releases[].text-representation` | object | Sometimes | `{language, script}` | — |
| `.tags` | array | Conditional (`inc=tags`) | Community tags; each `{name: string, count: integer}` | Sparsely populated for electronic music; can be useful for genre inference |
| `.genres` | array | Conditional (`inc=genres`) | Genre objects; each `{id, name, count}` | More structured than tags; coverage varies |
| `.ratings` | object | Conditional (`inc=ratings`) | `{votes-count: integer, value: float}` | Rarely populated |

**Fields NOT returned by MusicBrainz recording lookup:**
- `label` and `catalog-number` — require a separate release lookup with `inc=labels`
- `bpm`, `key`, `energy` — not in MusicBrainz at all; come from Essentia
- `genre` as a clean field — only as community tags/genres, variable quality

---

### Crate Candidate Fields Cross-Reference

| Crate field | Source | JSON path | Notes |
|-------------|--------|-----------|-------|
| `title` | MusicBrainz recording | `.title` | Always present |
| `artist` | MusicBrainz recording | `.artist-credit[].name` + `joinphrase` | Always present (with `inc=artist-credits`); must be assembled from credits array |
| `album` | MusicBrainz release group | `.releases[].title` or release group title | Available on releases; select "most relevant" release (see Full Lookup Flow) |
| `label` | MusicBrainz release | separate release lookup `.label-info[].label.name` | Requires extra API call per release |
| `catalogue_number` | MusicBrainz release | separate release lookup `.label-info[].catalog-number` | American spelling; requires extra API call |
| `year` | MusicBrainz recording | `.first-release-date` | Year-level precision usually available; may be partial |
| `genre` | MusicBrainz recording | `.genres[].name` or `.tags[].name` | Community-contributed; sparse for electronic music |
| `isrc` | MusicBrainz recording | `.isrcs[0]` | Often missing for electronic music |
| `duration` | AcoustID or MusicBrainz | AcoustID: `.results[].recordings[].duration` (seconds); MB: `.length` (milliseconds) | AcoustID gives integer seconds; MB gives milliseconds |
| `mb_recording_id` | AcoustID | `.results[].recordings[].id` | Core output of AcoustID lookup |
| `mb_release_id` | MusicBrainz recording | `.releases[0].id` | Multiple releases available; selection logic needed |
| `mb_artist_id` | MusicBrainz recording | `.artist-credit[0].artist.id` | First artist's MBID |

**Fields not on Crate's initial list but worth storing:**

| Field | Source | Reason to store |
|-------|--------|-----------------|
| `mb_release_group_id` | MusicBrainz recording → release | Stable identifier for "the album" across multiple pressings |
| `release_status` | MusicBrainz release | Distinguishes official from bootleg/promo |
| `release_country` | MusicBrainz release | Useful for DJ context (import, original pressing) |
| `acoustid_id` | AcoustID | The fingerprint identity; store for re-lookup / debugging |
| `acoustid_score` | AcoustID | Match confidence; store to know how reliable the identification was |
| `first_release_date` | MusicBrainz recording | `.first-release-date` — more reliable than release-level date for "year" |
| `artist_sort_name` | MusicBrainz artist | Needed for library sorting (e.g. "The" prefix handling) |

---

## Full Lookup Flow

Step-by-step from audio file to full metadata.

### Prerequisites

```python
import acoustid
import musicbrainzngs
musicbrainzngs.set_useragent("CrateApp", "0.1", "your@email.com")
```

---

### Step 1: Fingerprint the File

```python
duration, fingerprint = acoustid.fingerprint_file(path)
```

- `path`: absolute path to the audio file
- Returns `(float, string)` — duration in seconds, Chromaprint fingerprint string
- **On failure**: raises `FingerprintGenerationError` (or `NoBackendError` if fpcalc
  and Chromaprint library are both absent)
- **Short files**: Chromaprint can fingerprint files shorter than the standard 120s
  window; the `maxlength` parameter controls how much audio is used

---

### Step 2: Query AcoustID

```python
response = acoustid.lookup(
    apikey=ACOUSTID_API_KEY,
    fingerprint=fingerprint,
    duration=int(duration),
    meta=["recordings", "releasegroups"],
    timeout=10
)
```

- Returns the full parsed JSON dict
- **On no match**: `response["results"]` is `[]` — handle this explicitly
- **On failure**: raises `WebServiceError`
- **Rate limit**: pyacoustid enforces 3 req/s internally; no manual sleep needed

---

### Step 3: Extract the Best Recording ID

```python
results = response.get("results", [])
if not results:
    # No match — track is not in AcoustID database
    # Store acoustid_score = None, mb_recording_id = None
    # Proceed to file tag fallback

best = max(results, key=lambda r: r["score"])
score = best["score"]
acoustid_id = best["id"]

recordings = best.get("recordings", [])
if not recordings:
    # AcoustID has a fingerprint match but it's not linked to any MusicBrainz recording
    # Store acoustid_id and score; mb_recording_id = None

recording = recordings[0]  # Take the first (only one in most cases)
mb_recording_id = recording["id"]
```

When `results` has multiple entries with close scores, take the highest-scoring one.
When a result has multiple recordings, they represent multiple interpretations of the
same fingerprint — the first is usually correct, but this is a known ambiguity.

---

### Step 4: Query MusicBrainz

```python
result = musicbrainzngs.get_recording_by_id(
    mb_recording_id,
    includes=["artist-credits", "releases", "isrcs", "tags", "genres"]
)
recording = result["recording"]
```

- **On 404 (recording deleted/merged)**: raises `musicbrainzngs.ResponseError`
- **On network error**: raises `musicbrainzngs.NetworkError`
- **Rate limit**: musicbrainzngs does NOT enforce the 1 req/s limit internally;
  you must add `time.sleep(1)` between calls yourself

---

### Step 5: Extract Fields from MusicBrainz Response

```python
# Title
title = recording.get("title")

# Duration (milliseconds → seconds)
length_ms = recording.get("length")
duration_s = length_ms / 1000 if length_ms else None

# First release year
first_date = recording.get("first-release-date", "")
year = int(first_date[:4]) if first_date and len(first_date) >= 4 else None

# Artist name (assemble from credits)
credits = recording.get("artist-credit", [])
artist = "".join(c.get("name", "") + c.get("joinphrase", "") for c in credits).strip()

# Artist MBID (first credited artist)
mb_artist_id = credits[0]["artist"]["id"] if credits else None

# ISRC (first one if multiple)
isrcs = recording.get("isrcs", [])
isrc = isrcs[0] if isrcs else None

# Genres / tags
genres = [g["name"] for g in recording.get("genres", [])]
tags = [t["name"] for t in recording.get("tags", [])]

# Releases — pick best release for label/catalogue lookup
releases = recording.get("releases", [])
# Strategy: prefer "Official" status, then earliest date
official_releases = [r for r in releases if r.get("status") == "Official"]
candidates = official_releases if official_releases else releases
candidates_with_date = [r for r in candidates if r.get("date")]
best_release = min(candidates_with_date, key=lambda r: r["date"]) if candidates_with_date else (candidates[0] if candidates else None)

mb_release_id = best_release["id"] if best_release else None
```

---

### Step 6: Fetch Label and Catalogue Number (Optional Separate Call)

Only needed if label/catalogue data is required and the release ID is known:

```python
if mb_release_id:
    time.sleep(1)  # Respect MusicBrainz 1 req/s limit
    release_result = musicbrainzngs.get_release_by_id(
        mb_release_id,
        includes=["labels"]
    )
    release = release_result["release"]
    label_info = release.get("label-info", [])
    if label_info:
        label = label_info[0].get("label", {}).get("name")
        catalogue_number = label_info[0].get("catalog-number")
    else:
        label = None
        catalogue_number = None
```

Note: This is a second API call to MusicBrainz. For a high-volume import, batching or
caching release data is advisable.

---

### Failure Path Summary

| Situation | What happens | What to store |
|-----------|-------------|---------------|
| `FingerprintGenerationError` | File could not be decoded | Skip audio ID; use file tags only |
| `NoBackendError` | fpcalc/Chromaprint not installed | Fatal config error; stop import until fixed |
| AcoustID returns `results: []` | Track not in AcoustID database | `acoustid_score = None`, `mb_recording_id = None` |
| AcoustID result has no `recordings` | Fingerprint not linked to MB | `acoustid_id` stored, `mb_recording_id = None` |
| AcoustID `WebServiceError` | Network/API failure | Retry once; if still failing, skip and log |
| MusicBrainz `ResponseError` (404) | Recording deleted or merged | `mb_recording_id` stored but metadata = None; re-lookup later |
| MusicBrainz `NetworkError` | Network failure | Retry with backoff |
| MusicBrainz 503 (rate limit) | Too many requests | Back off and retry; reduce request rate |
| Field missing from MB response | Data not in MusicBrainz | Store `None`; do not throw |

---

## Match Rate Reality

### What is Known

**AcoustID database coverage**: The database contains 21,055,209 linked recordings
(MusicBrainz recording IDs). This is drawn from MusicBrainz's total database.
MusicBrainz covers approximately 30 million recordings as of recent years.

**Coverage is crowd-sourced**: Fingerprints are submitted by users of tools like
MusicBrainz Picard, beets, and other tagging software. Coverage reflects what those
users have tagged and submitted — heavily weighted toward music with existing MusicBrainz
data and users who run tagging tools.

### For Electronic Music Specifically

**Confirmed from documentation**: No published data on AcoustID match rates broken down
by genre is available from AcoustID or MusicBrainz official sources.

**What can be reasonably inferred** (not confirmed from primary sources):

- **Major label electronic releases** (Warp, Mute, R&S, Kompakt, Ostgut Ton): coverage
  is generally good because MusicBrainz has strong data for these labels, and their
  releases have been widely tagged by beets/Picard users.

- **White label vinyl**: Very likely to have no AcoustID match. White labels are typically
  not entered into MusicBrainz (no title, no artist, no catalogue number), so even if a
  fingerprint exists, it cannot be linked to a recording. The AcoustID response will
  either have empty `results` or have a result with no `recordings`.

- **Promos**: Mixed. Commercially distributed promos from known labels may be in
  MusicBrainz and AcoustID. Private promos, reference copies, and advance tracks
  typically are not.

- **Old electronic music (pre-2000)**: Coverage is thinner than for contemporary releases,
  particularly for obscure labels from the early Chicago house and UK rave scenes. This is
  a known gap in MusicBrainz.

- **DJ edits and bootlegs**: Almost certainly not in AcoustID unless explicitly submitted.

- **DJ mixes / recorded sets**: Not fingerprinted as individual tracks. AcoustID
  fingerprints are per-track, not per-mix segment.

**The no-match response is unambiguous**: An empty `results: []` array means "not found".
There is no distinct error code for "fingerprint didn't match" vs "not in database" — both
produce empty results. However, AcoustID fingerprinting is generally reliable for
commercially produced audio; a "no match" almost certainly means the track is not in the
database rather than a fingerprinting error.

**Implication for Crate**: Plan to handle a significant fraction of no-match results
(estimated 30–60% for a typical techno/house DJ library, based on the above reasoning —
this estimate is not from primary sources and should be validated in Phase 2 with real
tracks). The pipeline must not fail or stall on no-match; it should fall through to
file tag data gracefully.

---

## Installation

### Python libraries

Using uv (recommended for this project):

```bash
uv add pyacoustid musicbrainzngs
```

Or with pip:

```bash
pip install pyacoustid musicbrainzngs
```

### fpcalc (Chromaprint binary)

fpcalc must be installed separately. pyacoustid does not bundle it.

**WSL2 / Ubuntu / Debian:**

```bash
sudo apt install libchromaprint-tools
```

This installs `fpcalc` to `/usr/bin/fpcalc`. No further configuration is needed —
pyacoustid will find it on `$PATH`.

**Alternative (build from source or download binary):**

```bash
# Download precompiled binary from https://acoustid.org/chromaprint
# Extract and add to PATH, or set environment variable:
export FPCALC=/path/to/fpcalc
```

**macOS:**

```bash
brew install chromaprint
```

**Windows (native)**: Download the Windows binary from https://acoustid.org/chromaprint.
Note that Essentia (and therefore the full Crate pipeline) requires WSL2 on Windows;
install fpcalc inside WSL2 via apt.

### Verification Script

Save as `scripts/verify_acoustid.py` and run with a short audio file:

```python
#!/usr/bin/env python3
"""Verify AcoustID fingerprinting and lookup are working."""
import sys
import acoustid
import musicbrainzngs

ACOUSTID_API_KEY = "your_key_here"  # From https://acoustid.org/api-key

musicbrainzngs.set_useragent("CrateApp", "0.1", "your@email.com")

audio_file = sys.argv[1]

print(f"Fingerprinting {audio_file}...")
try:
    duration, fingerprint = acoustid.fingerprint_file(audio_file)
    print(f"  Duration: {duration:.1f}s")
    print(f"  Fingerprint: {fingerprint[:40]}...")
except acoustid.NoBackendError:
    print("ERROR: fpcalc not found. Install with: sudo apt install libchromaprint-tools")
    sys.exit(1)
except acoustid.FingerprintGenerationError as e:
    print(f"ERROR: Could not fingerprint file: {e}")
    sys.exit(1)

print("Querying AcoustID...")
try:
    response = acoustid.lookup(
        ACOUSTID_API_KEY,
        fingerprint,
        int(duration),
        meta=["recordings", "releasegroups"],
        timeout=10
    )
except acoustid.WebServiceError as e:
    print(f"ERROR: AcoustID API call failed: {e}")
    sys.exit(1)

results = response.get("results", [])
if not results:
    print("No match found in AcoustID database.")
else:
    best = max(results, key=lambda r: r["score"])
    print(f"  Score: {best['score']:.3f}")
    print(f"  AcoustID: {best['id']}")
    recordings = best.get("recordings", [])
    if recordings:
        rec = recordings[0]
        print(f"  MB Recording ID: {rec['id']}")
        print(f"  Title: {rec.get('title', '(none)')}")
        artists = rec.get("artists", [])
        if artists:
            print(f"  Artist: {artists[0].get('name', '(none)')}")

print("Done.")
```

Run with:

```bash
python scripts/verify_acoustid.py /path/to/track.mp3
```

---

## Open Questions

These cannot be confirmed from documentation alone and require real testing in Phase 2.

1. **Match rate on the actual Crate library**: What fraction of tracks in a typical
   techno/house library get an AcoustID match? The estimated 30–60% no-match rate above
   is unconfirmed. Test with 50+ representative tracks.

2. **AcoustID score threshold**: At what score value does a match become reliable?
   The documentation does not specify. Test whether scores below 0.7 are acceptable
   or produce false positives.

3. **Multiple recordings per result**: When a result has multiple recordings, is the
   first one always the correct one? Test with known tracks that have been released
   on multiple formats.

4. **`duration` units — AcoustID vs MusicBrainz**: AcoustID recordings return `duration`
   in **seconds** (integer); MusicBrainz returns `length` in **milliseconds** (integer).
   Confirm this difference with a real track to avoid unit errors in the pipeline.

5. **Label/catalogue coverage for electronic music**: How often is `label-info` populated
   for techno and house releases? For obscure labels, is `catalog-number` typically present?

6. **ISRCs for electronic music**: ISRCs are frequently absent for white labels and small
   labels. What fraction of tracks in a typical DJ library will have an ISRC? Measure in Phase 2.

7. **Genre/tag coverage**: Are tags and genres populated for electronic music releases in
   MusicBrainz? Quality and coverage for techno/house subgenres is unknown.

8. **MusicBrainz rate limit in practice**: Does musicbrainzngs enforce the 1 req/s limit
   internally, or must it be enforced manually? Confirm with a rapid-fire test. (The
   library source does not show internal rate limiting, unlike pyacoustid.)

9. **Release selection logic**: When a recording has 15+ linked releases (common for
   popular tracks), what is the best heuristic for picking the "right" one for a DJ
   library? (Earliest official, original market, etc.) Needs validation on real data.

10. **fpcalc minimum file length**: Is there a minimum audio length for a valid fingerprint?
    What happens with very short clips (under 10 seconds)?
