# Discogs Research

Researched: 2026-04-04
Author: Ivor Vice Bulaja

All findings are derived directly from the sources listed below. Where a source
could not be fetched (Cloudflare blocking), this is noted and the claim is attributed
to an alternative source.

---

## Sources

- Discogs API root: https://api.discogs.com/ (fetched directly)
- Discogs developer docs: https://www.discogs.com/developers/ (Cloudflare-blocked; data sourced from API calls and search results)
- Discogs API Terms of Use: https://support.discogs.com/hc/en-us/articles/360009334593-API-Terms-of-Use (referenced via search)
- Discogs Database Guidelines — Format: https://support.discogs.com/hc/en-us/articles/360005006654-Database-Guidelines-6-Format (referenced via search)
- Discogs Database Guidelines — Genres/Styles: https://support.discogs.com/hc/en-us/articles/360005055213-Database-Guidelines-9-Genres-Styles (referenced via search)
- Discogs Wikipedia article: https://en.wikipedia.org/wiki/Discogs (fetched via search)
- python3-discogs-client GitHub (joalla): https://github.com/joalla/discogs_client (fetched directly)
- python3-discogs-client ReadTheDocs: https://python3-discogs-client.readthedocs.io/en/latest/ (Cloudflare-blocked; content sourced via search)
- Rate limiting docs: https://python3-discogs-client.readthedocs.io/en/v2.3.15/requests_rate_limit.html (referenced via search)
- Authentication docs: https://python3-discogs-client.readthedocs.io/en/latest/authentication.html (referenced via search)
- Live API responses: fetched directly with curl against api.discogs.com (unauthenticated, 25 req/min limit)
  - Release 249504: https://api.discogs.com/releases/249504
  - Master 449968: https://api.discogs.com/masters/449968
  - Artist 72872: https://api.discogs.com/artists/72872
  - Label 895: https://api.discogs.com/labels/895
  - Artist 205 releases: https://api.discogs.com/artists/205/releases
  - Label 895 releases: https://api.discogs.com/labels/895/releases
  - Master 449968 versions: https://api.discogs.com/masters/449968/versions
  - Search: https://api.discogs.com/database/search (multiple queries)
- Discogs entity_type forum thread: https://www.discogs.com/forum/thread/399073
- Discogs genres/styles reference wiki: https://reference.discogs.com/wiki/style-guide-genre-electronic (unreachable; content referenced via search)

---

## What Discogs Is

Discogs is a community-built online database of music releases and a marketplace for
buying and selling physical music. It was founded in 2000 by Kevin Lewandowski,
originally focused exclusively on electronic music. The site expanded to other genres
from 2004 onward.

As of 2026 the database contains over 19.1 million release entries, approximately
9.96 million artist profiles, and around 2.24 million label entries. These figures
are returned live from https://api.discogs.com/.

**Who contributes data:** Every entry in the Discogs database is submitted by a
registered user. Contributors are required to have a physical copy of the release in
front of them when submitting. The New York Times described the model as
"Wikipedia-like." The database has contributions from over 347,000 people. Discogs
enforces strict database guidelines and a community moderation/voting system to
maintain data quality.

**Implications for reliability:** Because data is community-contributed, quality varies
by release. Well-documented releases on major labels tend to be accurate. Obscure
releases, white labels, and promos may be missing, incomplete, or have errors.
The `data_quality` field (documented below) provides a signal about the community's
assessment of each entry.

**Data model — entities:**

| Entity | Description |
|---|---|
| Release | A specific, physical or digital release of a recording. Includes format, label, catno, country, year. Multiple releases can share the same Master. |
| Master Release | The canonical grouping of all versions/pressings of the same recording. Contains the "main" release and links all related releases via the `versions` sub-endpoint. |
| Artist | A person, band, or collective. Includes real name, profile, name variations, group memberships, aliases, URLs. |
| Label | A record label or company. Includes profile, contact info, sublabels, parent label. |
| Track | A track on a release. Part of the `tracklist` array on a release object; not a standalone API entity. |

**Release vs. Master Release:**
A Release is a specific pressing: one label, one catno, one country, one year, one
format. A Master Release groups all pressings of the same recording. For example,
Jeff Mills "The Bells" has one Master (ID 449968) and multiple releases (616407,
35599327, 402964, etc.) with different formats, years, and caTNOs.

Releases that have never been assigned a Master have `master_id: 0` and
`master_url: null` in search results.

**What Discogs is strongest on:**
- Physical formats: vinyl (all sizes), CD, cassette
- Label and catalogue number data — extremely strong for vinyl releases
- Electronic music — Discogs originated as an electronic music database and has
  the most comprehensive coverage for this genre
- Collector-grade detail: matrix/runout etchings, pressing variants, sleeve notes

**What Discogs is weaker on:**
- Genre/style tagging — not all releases have styles assigned, especially
  older or obscure releases
- BPM, key, and other audio features — not in Discogs at all
- Streaming or licensing metadata (ISRC etc.) — rare

---

## Authentication and API Access

**Three authentication modes:**

### 1. Unauthenticated

No credentials required. Confirmed via live API testing: both database search and
release/artist/label endpoints respond without any authentication token. Rate limit
is 25 requests per minute. The `X-Discogs-Ratelimit: 25` header was confirmed in
live responses.

Some sources indicate the `/database/search` endpoint requires authentication. Live
testing on 2026-04-04 showed search working without authentication at 25 req/min.
The requirement may have been relaxed or may apply only when using a `q=` parameter
without other filters. **Confirm this empirically before relying on unauthenticated
search in production.**

### 2. Personal Access Token (User-Token)

Generate a token at: Discogs website → Settings → Developer Settings → Generate Token.

Pass the token in the Authorization header:
```
Authorization: Discogs token=YOUR_TOKEN_HERE
```

Alternative: pass as query parameter `?token=YOUR_TOKEN`. Not recommended for
production as tokens appear in URLs and logs.

Grants: 60 requests per minute. Also grants access to personal collection,
wantlist, and marketplace endpoints.

### 3. OAuth 1.0a

Full OAuth flow for applications acting on behalf of multiple users. Requires
a consumer key and consumer secret obtained from the Discogs developer settings.

OAuth flow:
1. Request a request token from Discogs OAuth endpoint
2. Redirect user to authorize URL
3. Receive OAuth verifier via callback
4. Exchange request token + verifier for access token + secret
5. Use access token + secret to sign all subsequent requests

The `identity()` method in python3-discogs-client is used to verify a completed
OAuth authentication.

Grants: 60 requests per minute per source IP.

**HTTPS requirement:** All authenticated requests must use HTTPS. Sending credentials
over HTTP is not supported.

**User-Agent requirement:** Applications must supply a unique, descriptive User-Agent
string. Generic user agents (e.g. curl/7.x, python-requests) are subject to more
severe rate limiting and may not see accurate rate limit headers. Format:
```
AppName/Version (contact@email.com)
```
Example: `CrateApp/0.1 (your@email.com)`

**Terms of Service restrictions (from API ToS, referenced via search):**

- No reselling of API access to third parties
- No charging fees for applications that rely on Discogs-provided data unless
  Discogs expressly permits it
- No using the API to drive traffic to non-Discogs websites
- Attempting to circumvent rate limits by creating additional API keys is prohibited
- Scraping (bypassing the API) is prohibited
- Commercial use is permitted but Discogs may restrict it at their discretion

---

## Rate Limits

Confirmed from live response headers (`X-Discogs-Ratelimit: 25`) and documented via
search results.

| Authentication | Requests per minute |
|---|---|
| Unauthenticated | 25 |
| Personal Access Token | 60 |
| OAuth | 60 |

**Rate limit window:** Moving average over a 60-second window. If no requests are
made for 60 seconds, the window resets.

**Response when exceeded:** HTTP 429 Too Many Requests (not confirmed from live
testing; inferred from common API practice and referenced in forum discussions).

**Rate limit headers returned on every response:**

| Header | Description |
|---|---|
| `X-Discogs-Ratelimit` | Total requests allowed per minute in current window |
| `X-Discogs-Ratelimit-Used` | Requests made in the current window |
| `X-Discogs-Ratelimit-Remaining` | Requests remaining in the current window |

Confirmed from live response:
```
x-discogs-ratelimit: 25
x-discogs-ratelimit-remaining: 16
x-discogs-ratelimit-used: 9
```

**Guidance for automated import pipeline:**
- Use authenticated access (personal access token) to get 60 req/min
- Check `X-Discogs-Ratelimit-Remaining` before each request and back off when low
- python3-discogs-client has built-in backoff/retry on rate limit hit (enabled by
  default; can be disabled via `client.backoff_enabled = False`)
- For a DJ library import of 5,000–20,000 tracks, budget approximately 2–4 API
  calls per track (search + release fetch, optionally master). At 60 req/min
  authenticated, 20,000 tracks × 3 calls = 60,000 requests ÷ 60 = 1,000 minutes
  (~16.7 hours) at maximum rate. Parallelize with care and spread imports over time.

---

## Search Endpoint Reference

**Endpoint:**
```
GET https://api.discogs.com/database/search
```

**Authentication:** Required per official docs (authentication starting August 2015
for search). Confirmed to work unauthenticated in testing on 2026-04-04 at 25 req/min.
Use authenticated for production.

### Query Parameters

All parameters are optional individually but at least one is required in practice.

| Parameter | Description |
|---|---|
| `q` | General full-text search query |
| `type` | Filter by entity type: `release`, `master`, `artist`, `label` |
| `title` | Search by combined "Artist - Title" string |
| `release_title` | Search by release title only |
| `artist` | Search by artist name |
| `anv` | Search by artist name variation |
| `label` | Search by label name |
| `genre` | Filter by genre (e.g. `Electronic`) |
| `style` | Filter by style (e.g. `Techno`, `House`) |
| `country` | Filter by country (e.g. `UK`, `US`, `Germany`) |
| `year` | Filter by year (exact year as string: `1993`) |
| `format` | Filter by format name (e.g. `Vinyl`, `CD`) |
| `catno` | Search by catalogue number |
| `barcode` | Search by barcode |
| `track` | Search by track title |
| `submitter` | Filter by submitter username |
| `contributor` | Filter by contributor username |
| `page` | Page number (1-based) |
| `per_page` | Results per page (default: 50, maximum: 100) |

Confirmed from live testing:
- `catno=PM-020&artist=Jeff+Mills` returns 2 results correctly
- `barcode=5012394144777` returns 8 results correctly
- `style=Techno` returns 551,873 releases across 5,000 pages
- `format=12%22&style=Techno&year=1993` returns 4,418 results
- `q=nonexistenttrackxyzabc123` returns `{"pagination":{"items":0},"results":[]}`

### Search Result Object (type=release)

Confirmed from live API responses:

```json
{
  "country": "US",
  "year": "2006",
  "format": ["Vinyl", "12\"", "33 ⅓ RPM"],
  "label": ["Purpose Maker", "Millsart"],
  "type": "release",
  "genre": ["Electronic"],
  "style": ["Tribal", "Techno"],
  "id": 616407,
  "barcode": ["PM 020-A (u) (NSC)"],
  "master_id": 449968,
  "master_url": "https://api.discogs.com/masters/449968",
  "uri": "/release/616407-Jeff-Mills-The-Bells-10th-Anniversary",
  "catno": "PM-020",
  "title": "Jeff Mills - The Bells (10th Anniversary)",
  "thumb": "",
  "cover_image": "",
  "resource_url": "https://api.discogs.com/releases/616407",
  "community": {
    "want": 2246,
    "have": 1423
  },
  "format_quantity": 1,
  "formats": [
    {
      "name": "Vinyl",
      "qty": "1",
      "descriptions": ["12\"", "33 ⅓ RPM"]
    }
  ]
}
```

**Notes on search result fields:**

- `format` (top-level): flat array of all format strings merged from the `formats`
  objects. E.g. `["Vinyl", "12\"", "33 ⅓ RPM"]`.
- `label` (top-level): flat array of all label names. May include distributor, manufacturer etc.
- `catno`: single string representing the primary catalogue number.
- `barcode`: array of all barcodes and identifiers (barcodes, matrix runouts, price codes all merged).
- `thumb` and `cover_image`: often empty strings for releases without images or when
  unauthenticated. Confirmed empty in live unauthenticated responses.
- `uri`: relative path (not full URL). Full URL is `https://www.discogs.com` + `uri`.
- `master_id`: integer. `0` and `master_url: null` when no master release exists.
- `community.want` / `community.have`: integers. Present in search results without authentication.
- `format_quantity`: integer count of format items.
- `formats`: structured array (same structure as in the full release endpoint).
- Fields **not** present in search results (only on full release endpoint):
  `artists`, `extraartists`, `tracklist`, `identifiers`, `videos`, `images`,
  `notes`, `released`, `released_formatted`, `date_added`, `date_changed`,
  `num_for_sale`, `lowest_price`, `estimated_weight`, `blocked_from_sale`,
  `is_offensive`, `companies`, `series`, `artists_sort`.

### Pagination Object

```json
{
  "pagination": {
    "page": 1,
    "pages": 10,
    "per_page": 50,
    "items": 472,
    "urls": {
      "last": "https://api.discogs.com/database/search?...&page=10",
      "next": "https://api.discogs.com/database/search?...&page=2"
    }
  }
}
```

- `urls` object contains `first`, `last`, `prev`, `next` links as applicable.
  `first` and `prev` are absent on the first page; `next` and `last` are absent on
  the last page.
- Maximum `per_page`: 100 (confirmed: requesting 500 returns 100).

### Zero-Results Response

Confirmed from live testing:
```json
{
  "pagination": {
    "page": 1,
    "pages": 1,
    "per_page": 50,
    "items": 0,
    "urls": {}
  },
  "results": []
}
```

`urls` is an empty object `{}` when there are no results or only one page.

---

## Release Endpoint Reference

**Endpoint:**
```
GET https://api.discogs.com/releases/{release_id}
```

Example: https://api.discogs.com/releases/249504

### Complete Field List

Confirmed from live API response for release 249504:

**Top-level scalar fields:**

| Field | Type | Presence | Description |
|---|---|---|---|
| `id` | integer | always | Discogs release ID |
| `status` | string | always | Release status. Confirmed value: `"Accepted"`. Other possible values not confirmed from live data. |
| `year` | integer | usually | Release year. May be absent on incomplete entries. |
| `title` | string | always | Release title (does not include artist name) |
| `country` | string | sometimes | Country of release (e.g. `"UK"`, `"US"`, `"Europe"`) |
| `released` | string | sometimes | Full release date, e.g. `"1987-07-00"`. Day may be `00` when unknown. |
| `released_formatted` | string | sometimes | Human-readable date, e.g. `"Jul 1987"` |
| `notes` | string | sometimes | Free-text notes entered by contributors. Can be long. |
| `data_quality` | string | always | Community data quality vote (see Data Quality Signals) |
| `master_id` | integer | sometimes | Master release ID. Absent if no master exists. |
| `master_url` | string | sometimes | URL of master release. Absent if no master exists. |
| `uri` | string | always | Full URL on www.discogs.com |
| `resource_url` | string | always | Full API URL for this release |
| `artists_sort` | string | always | Artist name(s) in sort-order format |
| `format_quantity` | integer | always | Count of format items |
| `date_added` | string (ISO 8601) | always | When first submitted to database |
| `date_changed` | string (ISO 8601) | always | When last modified |
| `num_for_sale` | integer | always | Number of copies currently listed on marketplace |
| `lowest_price` | float or null | always | Lowest marketplace price in USD. `null` when none for sale. |
| `estimated_weight` | integer | sometimes | Estimated shipping weight in grams |
| `blocked_from_sale` | boolean | always | Whether blocked from marketplace |
| `is_offensive` | boolean | always | Whether flagged as offensive content |
| `thumb` | string | always | URL of thumbnail image (150x150). May be empty string. |

**`artists` array** — artists credited on the release:

| Field | Type | Presence | Description |
|---|---|---|---|
| `id` | integer | always | Artist Discogs ID |
| `name` | string | always | Artist name as credited on this release |
| `anv` | string | always | Artist name variation used on this release. Empty string if same as canonical name. |
| `join` | string | always | Join phrase between artists (e.g. `"&"`, `","`, `"feat."`). Empty string for last/only artist. |
| `role` | string | always | Role (usually empty string for primary artists) |
| `tracks` | string | always | Which tracks this credit applies to. Empty string = all tracks. |
| `resource_url` | string | always | API URL of this artist |
| `thumbnail_url` | string | sometimes | Thumbnail image URL for artist |

**`extraartists` array** — credited personnel (producers, engineers, etc.):

Same fields as `artists` but `role` is always populated:

| Field | Description |
|---|---|
| `id` | Artist Discogs ID |
| `name` | Canonical artist name |
| `anv` | Name as credited on this release |
| `join` | Join phrase |
| `role` | Credit role, e.g. `"Producer, Written-By"`, `"Mixed By"`, `"Engineer"`, `"Lacquer Cut By"`, `"Design"` |
| `tracks` | Which tracks this credit applies to. Empty string = all tracks. |
| `resource_url` | API URL |

**`labels` array** — labels credited on the release:

| Field | Type | Presence | Description |
|---|---|---|---|
| `id` | integer | always | Label Discogs ID |
| `name` | string | always | Label name |
| `catno` | string | always | Catalogue number as printed on release. May be empty string. |
| `entity_type` | string | always | Numeric string identifying the type of company (see entity_type values below) |
| `entity_type_name` | string | always | Human-readable entity type, e.g. `"Label"` |
| `resource_url` | string | always | API URL of this label |
| `thumbnail_url` | string | sometimes | Thumbnail image URL for label |

**`formats` array** — physical/digital format:

| Field | Type | Presence | Description |
|---|---|---|---|
| `name` | string | always | Format type, e.g. `"Vinyl"`, `"CD"`, `"File"`, `"Cassette"` |
| `qty` | string | always | Quantity as string integer, e.g. `"1"`, `"2"` |
| `text` | string | sometimes | Free text description, e.g. `"Poster Bag"`, `"Green, Glow In Dark"`, `"320 kbps"` |
| `descriptions` | array of strings | sometimes | Format descriptors. See Format Vocabulary section. |

**`genres` array** — array of genre strings, e.g. `["Electronic"]`, `["Electronic", "Pop"]`.

**`styles` array** — array of style strings, e.g. `["Techno", "Tribal"]`, `["Euro-Disco"]`.

**`tracklist` array** — tracks on the release:

| Field | Type | Presence | Description |
|---|---|---|---|
| `position` | string | always | Track position, e.g. `"A"`, `"B1"`, `"1"`, `"A1"` |
| `type_` | string | always | Track type: `"track"` for normal tracks; `"heading"` for section headers; `"index"` for index tracks |
| `title` | string | always | Track title |
| `duration` | string | always | Duration as `"M:SS"` or `"H:MM:SS"`. Empty string if unknown. |
| `artists` | array | sometimes | Per-track artist credits (same structure as release `artists`) |
| `extraartists` | array | sometimes | Per-track extra credits |

No sub-tracks were observed in the test data. The `type_` field uses a trailing
underscore because `type` is a Python reserved word.

**`images` array** — release images:

| Field | Type | Presence | Description |
|---|---|---|---|
| `type` | string | always | `"primary"` or `"secondary"` |
| `uri` | string | always | Full-size image URL |
| `resource_url` | string | always | Same as `uri` (redundant) |
| `uri150` | string | always | 150x150 thumbnail URL |
| `width` | integer | always | Image width in pixels |
| `height` | integer | always | Image height in pixels |

**`videos` array** — linked YouTube videos:

| Field | Type | Presence | Description |
|---|---|---|---|
| `uri` | string | always | YouTube URL |
| `title` | string | always | Video title |
| `description` | string | always | Video description text |
| `duration` | integer | always | Duration in seconds |
| `embed` | boolean | always | Whether embedding is allowed |

**`community` object** — community statistics:

| Field | Type | Presence | Description |
|---|---|---|---|
| `have` | integer | always | Number of users who own this release |
| `want` | integer | always | Number of users who want this release |
| `rating.count` | integer | always | Number of community ratings |
| `rating.average` | float | always | Average community rating (scale unclear from data; observed range 1–5) |
| `submitter.username` | string | always | Username of original submitter |
| `submitter.resource_url` | string | always | API URL of submitter |
| `contributors` | array | always | Array of `{username, resource_url}` for all contributors |
| `data_quality` | string | always | Same `data_quality` value as top-level field |
| `status` | string | always | Same `status` value as top-level field |

**`identifiers` array** — barcodes, matrix numbers, and other identifiers:

| Field | Type | Presence | Description |
|---|---|---|---|
| `type` | string | always | Identifier type (see known types below) |
| `value` | string | always | The identifier value |
| `description` | string | sometimes | Additional context, e.g. `"A side label"`, `"variant 1"` |

Known `type` values observed in live data:
- `"Barcode"` — EAN/UPC barcode
- `"Matrix / Runout"` — vinyl matrix/runout etching
- `"Label Code"` — label code (LC number)
- `"Price Code"` — price code, often with region description
- `"ASIN"` — Amazon ASIN (observed in other releases)
- `"Rights Society"` — e.g. `"GEMA"`, `"BIEM"`, `"SACEM"`
- `"Mastering SID Code"` — CD mastering SID
- `"Mould SID Code"` — CD mould SID
- `"Other"` — catch-all

**`companies` array** — all related companies (distributors, manufacturers, etc.):

Same fields as `labels` array. The `entity_type` / `entity_type_name` fields
differentiate role:

Known `entity_type` → `entity_type_name` mappings (from forum documentation):

| entity_type | entity_type_name |
|---|---|
| 1 | Label |
| 2 | Series |
| 4 | Record Company |
| 5 | Licensed To |
| 6 | Licensed From |
| 7 | Licensed Through |
| 8 | Marketed By |
| 9 | Distributed By |
| 10 | Manufactured By |
| 11 | Exported By |
| 13 | Phonographic Copyright (p) |
| 14 | Copyright (c) |
| 16 | Made By |
| 17 | Pressed By |
| 18 | Duplicated By |
| 19 | Printed By |
| 21 | Published By |
| 23 | Recorded At |
| 24 | Engineered At |
| 25 | Overdubbed At |
| 26 | Produced At |
| 27 | Mixed At |
| 28 | Remixed At |
| 29 | Mastered At |
| 30 | Lacquer Cut At |
| 31 | Glass Mastered At |
| 33 | Designed At |
| 34 | Filmed At |
| 35 | Remastered At |
| 36 | Edited At |
| 37 | Produced For |

Confirmed from live data: entity_type `"13"` = `"Phonographic Copyright (p)"`,
entity_type `"14"` = `"Copyright (c)"`, entity_type `"9"` = `"Distributed By"`,
entity_type `"8"` = `"Marketed By"`, entity_type `"5"` = `"Licensed To"`,
entity_type `"4"` = `"Record Company"`, entity_type `"17"` = `"Pressed By"`,
entity_type `"30"` = `"Lacquer Cut At"`, entity_type `"21"` = `"Published By"`.

**`series` array** — series this release belongs to. Same structure as `labels`.
Empty array `[]` when release is not part of a series (confirmed from live data).

---

## Master Release Endpoint Reference

**Endpoint:**
```
GET https://api.discogs.com/masters/{master_id}
```

Example: https://api.discogs.com/masters/449968

### Complete Field List

Confirmed from live API response:

| Field | Type | Presence | Description |
|---|---|---|---|
| `id` | integer | always | Master release ID |
| `title` | string | always | Title |
| `year` | integer | always | Year of first release |
| `data_quality` | string | always | Data quality (same values as release) |
| `uri` | string | always | Full URL on www.discogs.com |
| `resource_url` | string | always | API URL |
| `versions_url` | string | always | URL of the versions sub-endpoint |
| `main_release` | integer | always | Release ID of the main/canonical release |
| `main_release_url` | string | always | API URL of main release |
| `most_recent_release` | integer | always | Release ID of most recent version |
| `most_recent_release_url` | string | always | API URL of most recent release |
| `num_for_sale` | integer | always | Number of copies for sale across all versions |
| `lowest_price` | float | always | Lowest price across all versions |
| `images` | array | sometimes | Same structure as release images |
| `genres` | array | always | Genre strings |
| `styles` | array | always | Style strings |
| `tracklist` | array | always | Same structure as release tracklist |
| `artists` | array | always | Same structure as release artists |
| `videos` | array | sometimes | Same structure as release videos |

**Versions sub-endpoint:**
```
GET https://api.discogs.com/masters/{master_id}/versions
```

Confirmed from live response for master 449968:

Returns paginated list of releases. Each version object:

| Field | Type | Description |
|---|---|---|
| `id` | integer | Release ID |
| `title` | string | Title |
| `label` | string | Primary label |
| `country` | string | Country |
| `major_formats` | array | Primary format names, e.g. `["Vinyl"]`, `["DVDr"]` |
| `format` | string | Human-readable format summary, e.g. `"12\", 33 ⅓ RPM"` |
| `catno` | string | Catalogue number |
| `released` | string | Release year (as string) |
| `status` | string | Release status |
| `resource_url` | string | API URL of this release |
| `thumb` | string | Thumbnail URL |
| `stats.community.in_wantlist` | integer | Users who want this version |
| `stats.community.in_collection` | integer | Users who own this version |

The versions response also includes `filters`, `filter_facets` objects for
server-side filtering by format, label, country, and released year.

**When a release has no master:**
`master_id` is absent (or 0 in search results) and `master_url` is null. There is no
master release object to fetch.

---

## Artist Endpoint Reference

**Endpoint:**
```
GET https://api.discogs.com/artists/{artist_id}
```

Example: https://api.discogs.com/artists/72872

### Complete Field List

Confirmed from live API response:

| Field | Type | Presence | Description |
|---|---|---|---|
| `id` | integer | always | Artist Discogs ID |
| `name` | string | always | Canonical artist name |
| `realname` | string | sometimes | Real name (for persons). Absent for groups/bands. |
| `profile` | string | always | Free-text biography (may use Discogs BBCode markup) |
| `data_quality` | string | always | Data quality vote |
| `uri` | string | always | Full URL on www.discogs.com |
| `resource_url` | string | always | API URL |
| `releases_url` | string | always | URL of the releases sub-endpoint |
| `urls` | array of strings | sometimes | External URLs (website, social media, Wikipedia, etc.) |
| `namevariations` | array of strings | sometimes | Alternative spellings/variations of name |
| `aliases` | array of objects | sometimes | Artist aliases: `{id, name, resource_url}` |
| `groups` | array of objects | sometimes | Groups this artist is a member of: `{id, name, resource_url, active}` |
| `members` | array of objects | sometimes | Members of this group (for bands): `{id, name, resource_url, active}` |
| `images` | array | sometimes | Same structure as release images |

**Releases sub-endpoint:**
```
GET https://api.discogs.com/artists/{artist_id}/releases
```

Confirmed from live response for artist 205 (Jeff Mills):

Returns paginated list. Each item:

| Field | Type | Description |
|---|---|---|
| `id` | integer | Release or master ID |
| `title` | string | Title |
| `type` | string | `"release"` or `"master"` |
| `main_release` | integer | (masters only) Main release ID |
| `artist` | string | Artist name string |
| `role` | string | Artist role, e.g. `"Main"`, `"Remix"`, `"Appearance"` |
| `resource_url` | string | API URL |
| `year` | integer | Year |
| `thumb` | string | Thumbnail URL |
| `label` | string | (releases only) Primary label name |
| `format` | string | (releases only) Format summary string |
| `status` | string | (releases only) Status |
| `stats.community.in_wantlist` | integer | Users who want |
| `stats.community.in_collection` | integer | Users who own |

---

## Label Endpoint Reference

**Endpoint:**
```
GET https://api.discogs.com/labels/{label_id}
```

Example: https://api.discogs.com/labels/895

### Complete Field List

Confirmed from live API response:

| Field | Type | Presence | Description |
|---|---|---|---|
| `id` | integer | always | Label Discogs ID |
| `name` | string | always | Label name |
| `profile` | string | always | Free-text description of the label (may be empty string) |
| `contact_info` | string | sometimes | Contact information text (may be empty string) |
| `uri` | string | always | Full URL on www.discogs.com |
| `resource_url` | string | always | API URL |
| `releases_url` | string | always | URL of the releases sub-endpoint |
| `data_quality` | string | always | Data quality vote |
| `images` | array | sometimes | Same structure as release images |
| `urls` | array of strings | sometimes | External URLs |
| `sublabels` | array | sometimes | Sub-labels: `{id, name, resource_url}`. Array of objects. |
| `parent_label` | object | sometimes | Parent label: `{id, name, resource_url}`. Absent if no parent. |

Confirmed from live data:
- `parent_label` example: `{"id": 29073, "name": "Sony Music Entertainment", "resource_url": "..."}`
- `sublabels` confirmed to be an array of `{id, name, resource_url}` objects.

**Releases sub-endpoint:**
```
GET https://api.discogs.com/labels/{label_id}/releases
```

Confirmed from live response for label 895:

Returns paginated list. Each item:

| Field | Type | Description |
|---|---|---|
| `id` | integer | Release ID |
| `title` | string | Release title |
| `artist` | string | Artist name |
| `year` | integer | Year |
| `catno` | string | Catalogue number |
| `format` | string | Format summary string |
| `resource_url` | string | API URL |
| `thumb` | string | Thumbnail URL |
| `status` | string | Status |

---

## discogs_client Library Reference

**Library name:** python3-discogs-client
**Package name (PyPI):** `python3-discogs-client`
**GitHub:** https://github.com/joalla/discogs_client
**History:** Originally the official Discogs Python client. Deprecated by Discogs in
June 2020. The joalla/discogs_client fork continues active maintenance.

### Installation

```
uv add python3-discogs-client
# or
pip install python3-discogs-client
```

**Python version:** Python 3 only (the package name confirms this). Specific minimum
version not documented in sources reviewed.

### Authentication Setup

**User-token (quickest):**
```python
import discogs_client
d = discogs_client.Client('AppName/0.1', user_token='YOUR_TOKEN')
```

**OAuth:**
```python
d = discogs_client.Client(
    'AppName/0.1',
    consumer_key='YOUR_KEY',
    consumer_secret='YOUR_SECRET'
)
request_token, request_secret, url = d.get_authorize_url()
# Redirect user to url, receive oauth_verifier
access_token, access_secret = d.get_access_token(oauth_verifier)
# Verify
me = d.identity()  # Returns User object if OK
```

### Client Methods

| Method | Description |
|---|---|
| `d.release(release_id)` | Fetch a Release object by ID |
| `d.master(master_id)` | Fetch a MasterRelease object by ID |
| `d.artist(artist_id)` | Fetch an Artist object by ID |
| `d.label(label_id)` | Fetch a Label object by ID |
| `d.search(query, **kwargs)` | Search the database. Returns paginated results. |
| `d.identity()` | Returns the authenticated User object |
| `d.user(username)` | Fetch a User object |

### Search Method

```python
results = d.search('The Bells', type='release', artist='Jeff Mills')
# All parameters from the search endpoint are supported as kwargs
# results is a paginated list-like object
# results[0] → first result
# results.page(2) → fetch page 2
```

All search endpoint parameters are passable as keyword arguments.

### Object Types and Attributes

**Release:**

| Attribute | Description |
|---|---|
| `.id` | Release ID |
| `.title` | Title |
| `.year` | Year |
| `.country` | Country |
| `.status` | Status |
| `.data_quality` | Data quality |
| `.artists` | List of Artist objects (lazy-loaded) |
| `.labels` | List of Label objects (lazy-loaded) |
| `.genres` | List of genre strings |
| `.styles` | List of style strings |
| `.formats` | List of format dicts |
| `.tracklist` | List of Track objects |
| `.images` | List of image dicts |
| `.videos` | List of video dicts |
| `.notes` | Notes string |
| `.master` | MasterRelease object (lazy-loaded, if master exists) |
| `.companies` | List of company dicts |
| `.credits` | Credits/extraartists |
| `.marketplace_stats` | Marketplace statistics |
| `.url` | URL on www.discogs.com |
| `.fetch()` | Force fetch all data |
| `.refresh()` | Refresh data from API |
| `.data` | Raw response dict |

**MasterRelease:**

| Attribute | Description |
|---|---|
| `.id` | Master ID |
| `.title` | Title |
| `.year` | Year |
| `.data_quality` | Data quality |
| `.artists` | Artists (lazy-loaded) |
| `.genres` | Genres |
| `.styles` | Styles |
| `.images` | Images |
| `.tracklist` | Tracklist |
| `.main_release` | Release object for main release (lazy-loaded) |
| `.versions` | Paginated list of all version Release objects |
| `.url` | URL |

**Artist:**

| Attribute | Description |
|---|---|
| `.id` | Artist ID |
| `.name` | Name |
| `.realname` | Real name |
| `.profile` | Biography |
| `.data_quality` | Data quality |
| `.aliases` | List of Artist objects |
| `.groups` | List of Artist objects (groups this artist belongs to) |
| `.members` | List of Artist objects (members, if this is a group) |
| `.urls` | List of URL strings |
| `.namevariations` | List of name variation strings |
| `.images` | Images |
| `.releases` | Paginated list of releases |
| `.url` | URL |

**Label:**

| Attribute | Description |
|---|---|
| `.id` | Label ID |
| `.name` | Name |
| `.profile` | Description |
| `.contact_info` | Contact info |
| `.data_quality` | Data quality |
| `.urls` | List of URL strings |
| `.sublabels` | List of Label objects |
| `.parent_label` | Parent Label object (or None) |
| `.images` | Images |
| `.releases` | Paginated list of releases |
| `.url` | URL |

**Lazy loading:** Most nested objects are loaded on first access. Accessing
`release.artists[0].name` will trigger an HTTP request to fetch the artist if not
already loaded. Plan API call budgets accordingly.

### Exception Types

| Exception | When raised |
|---|---|
| `discogs_client.exceptions.HTTPError` | HTTP error from the API (e.g. 404 Not Found, 401 Unauthorized) |
| `discogs_client.exceptions.AuthorizationError` | OAuth authorization failure (e.g. invalid consumer key, bad verifier) |
| `discogs_client.exceptions.ConfigurationError` | Misconfiguration of the client |
| `discogs_client.exceptions.TooManyAttemptsError` | Rate limit backoff exceeded maximum retry attempts |

No `ScraperError` was found in official sources.

### Rate Limit Handling

The library has **built-in automatic backoff and retry** when rate limits are hit.
This is **enabled by default**.

```python
# Disable automatic backoff (not recommended for automated pipelines):
d.backoff_enabled = False
```

When rate limit is hit and backoff is enabled, the library sleeps and retries
automatically. When `TooManyAttemptsError` is raised, the maximum retries have been
exhausted.

### Maintenance Status

The joalla/discogs_client fork is actively maintained as of 2026. The original
discogs/discogs_client repo is deprecated and archived. Use the joalla fork.

---

## Image and Media URLs

**URL structure:** Discogs images are served from `i.discogs.com` with a URL-safe
base64-encoded path and optional resizing/quality parameters.

Example full-size:
```
https://i.discogs.com/-DPFA5hKT8i91jnjn4rLB1zSiuUBFTrGWspu1TpLV30/rs:fit/g:sm/q:90/h:600/w:600/czM6Ly9kaXNjb2dz...
```

Example thumbnail (150x150):
```
https://i.discogs.com/HG2xChKN-rIHHSfgL53W9z2vJWeFknfevpOMwSHtIaM/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz...
```

URL parameters observed:
- `rs:fit` — resize mode
- `g:sm` — gravity (smart/center)
- `q:90` or `q:40` — JPEG quality
- `h:NNN/w:NNN` — height/width constraints

**Image types:** `"primary"` (main image, usually front cover) and `"secondary"`
(additional images: back cover, labels, inserts, etc.).

**Authentication for images:** Image URLs themselves do not require authentication.
However, the `uri` and `uri150` fields may return empty strings in search results
when unauthenticated. Confirmed: full release endpoint returns populated image URLs
without authentication.

**Forum note:** Some forum discussions report 403 errors retrieving images. This is
believed to be related to hotlinking policies. Downloading images programmatically
for storage is likely acceptable but caching the URL and fetching on-demand may hit
restrictions. Not confirmed from official documentation.

---

## Genres and Styles Taxonomy

**Structure:** Genres are top-level classifications. Styles are sub-genres within
a genre. A release can have multiple genres and multiple styles.

**No dedicated API endpoint** exists for fetching the complete genre/style list.
The taxonomy is only enumerable via database dumps or by observation.

### All Top-Level Genres (from Discogs)

From Discogs search filter interface (referenced via search, not confirmed from
a direct API endpoint response):

- Blues
- Brass & Military
- Children's
- Classical
- Electronic
- Folk, World, & Country
- Funk / Soul
- Hip Hop
- Jazz
- Latin
- Non-Music
- Pop
- Reggae
- Rock
- Stage & Screen

### Electronic Genre — Styles

The following styles are confirmed to exist under the Electronic genre. This list
was assembled from live search results, the Discogs reference wiki (referenced via
search), and forum discussions. It is **not guaranteed to be exhaustive** — Discogs
has hundreds of accepted styles and the complete list requires database dump analysis.

Styles observed in live data:
- `Techno`
- `Tribal` (as used for Jeff Mills, distinct from "Techno" but co-assigned)
- `Euro-Disco`
- `Synth-pop`
- `Dance-pop`

Styles documented from search results and Discogs references:
- `Ambient`
- `Breakbeat`
- `Chicago House`
- `Deep House`
- `Detroit Techno`
- `Disco`
- `Dream House`
- `Drum n Bass`
- `Dub`
- `Dub Techno`
- `Electro`
- `Euro-Disco`
- `Euro House`
- `EBM` (Electronic Body Music)
- `Experimental`
- `Freestyle`
- `Funky House`
- `Gabber`
- `Garage House`
- `Happy Hardcore`
- `Hard House`
- `Hard Trance`
- `Hardcore`
- `Hi NRG`
- `House`
- `IDM` (Intelligent Dance Music)
- `Industrial`
- `Italo-Disco`
- `Jungle`
- `Minimal`
- `Minimal Techno`
- `Neo-Classical`
- `New Beat`
- `New Wave`
- `Nu-Disco`
- `Noise`
- `Progressive House`
- `Progressive Trance`
- `Psy-Trance`
- `Synth-pop`
- `Tech House`
- `Techno`
- `Trance`
- `Tribal`
- `Trip Hop`
- `UK Garage`

Styles commonly used for **techno** in the Discogs community:
`Techno`, `Detroit Techno`, `Minimal Techno`, `Dub Techno`, `Tribal`, `Industrial`,
`EBM`, `Tech House`, `Hard Trance`, `Gabber`

Styles commonly used for **house** in the Discogs community:
`House`, `Chicago House`, `Deep House`, `Garage House`, `Funky House`, `Tech House`,
`Progressive House`, `UK Garage`, `Disco`, `Euro House`, `Dream House`, `Nu-Disco`

**Note:** The complete canonical list is in the Discogs submission form dropdown and
database dumps. The list above covers the most common styles but is not exhaustive.

---

## Format Vocabulary

**Structure:** Each `formats` object has a `name` (the medium type) and a
`descriptions` array (attributes of that medium). A release can have multiple format
objects (e.g., a CD + booklet bundle).

### Known `name` Values (format medium types)

From live data and documented sources:
- `Vinyl`
- `CD`
- `CDr`
- `DVD`
- `DVDr`
- `File` (digital download)
- `Cassette`
- `VHS`
- `Laserdisc`
- `Box Set`
- `All Media` (used for multi-format sets)

### Known `descriptions` Values

Confirmed from live API responses and Discogs database guidelines:

**Vinyl size:**
`7"`, `10"`, `12"`, `16"`

**Speed:**
`33 ⅓ RPM`, `45 RPM`, `78 RPM`

**Release type:**
`LP`, `EP`, `Single`, `Album`, `Compilation`, `Maxi-Single`

**Special format attributes:**
`Promo`, `White Label`, `Limited Edition`, `Reissue`, `Repress`
`Stereo`, `Mono`, `Quadraphonic`
`Etched` (for etched/blank sides)
`Test Pressing`
`Numbered`
`Misprint`
`Record Store Day`
`Sampler`
`Mixed` (for mix compilations)

**CD/digital specific:**
`Enhanced` (with multimedia content), `HDCD`, `DualDisc`

**File format specific:**
`MP3`, `WAV`, `FLAC`, `AAC`, `AIFF`

**File release type:**
`Album`, `EP`, `Single`, `Compilation`

Confirmed from live data: `"Poster Bag"` appears in the `text` field (not
`descriptions`). `"Green, Glow In Dark"` and `"320 kbps"` also appear in `text`.

**Determining format from API data:**

| Release type | How to identify |
|---|---|
| 12" vinyl | `formats[n].name == "Vinyl"` AND `"12\""` in `formats[n].descriptions` |
| 7" vinyl | `formats[n].name == "Vinyl"` AND `"7\""` in `formats[n].descriptions` |
| LP | `formats[n].name == "Vinyl"` AND `"LP"` in `formats[n].descriptions` |
| CD single | `formats[n].name == "CD"` AND `"Single"` in `formats[n].descriptions` |
| Promo | `"Promo"` in `formats[n].descriptions` |
| White label | `"White Label"` in `formats[n].descriptions` |
| Digital | `formats[n].name == "File"` |
| 33 RPM | `"33 ⅓ RPM"` in `formats[n].descriptions` |

Note: The `format` (top-level flat array in search results) merges the `name` and
all `descriptions` values into one array. The structured `formats` array in the full
release endpoint separates them properly.

---

## Field Inventory

Complete inventory of fields across all endpoints. Presence: A=always, S=sometimes,
R=rarely.

### Search Result (type=release)

| JSON path | Type | Presence | Notes |
|---|---|---|---|
| `country` | string | S | ISO country or region name |
| `year` | string | S | Year as string |
| `format` | array[string] | S | Flat merged format array |
| `label` | array[string] | S | Flat label names array |
| `type` | string | A | Always `"release"` when type filter used |
| `genre` | array[string] | S | Genre strings |
| `style` | array[string] | S | Style strings (can be empty array) |
| `id` | integer | A | Release ID |
| `barcode` | array[string] | S | All barcodes/identifiers merged |
| `master_id` | integer | S | 0 when no master |
| `master_url` | string/null | S | null when no master |
| `uri` | string | A | Relative path |
| `catno` | string | S | Primary catalogue number |
| `title` | string | A | "Artist - Title" format in search results |
| `thumb` | string | A | Empty string when no image |
| `cover_image` | string | A | Empty string when no image |
| `resource_url` | string | A | Full API URL |
| `community.want` | integer | A | |
| `community.have` | integer | A | |
| `format_quantity` | integer | A | |
| `formats[].name` | string | A | |
| `formats[].qty` | string | A | |
| `formats[].text` | string | S | |
| `formats[].descriptions` | array | S | |

### Full Release

All search fields plus:

| JSON path | Type | Presence | Notes |
|---|---|---|---|
| `status` | string | A | |
| `artists_sort` | string | A | |
| `date_added` | string | A | ISO 8601 |
| `date_changed` | string | A | ISO 8601 |
| `num_for_sale` | integer | A | |
| `lowest_price` | float/null | A | |
| `notes` | string | S | |
| `released` | string | S | May have `00` day |
| `released_formatted` | string | S | |
| `master_id` | integer | S | Absent if no master |
| `master_url` | string | S | Absent if no master |
| `estimated_weight` | integer | S | Grams |
| `blocked_from_sale` | boolean | A | |
| `is_offensive` | boolean | A | |
| `thumb` | string | A | |
| `artists[].id` | integer | A | |
| `artists[].name` | string | A | |
| `artists[].anv` | string | A | Empty string if same as name |
| `artists[].join` | string | A | |
| `artists[].role` | string | A | Usually empty for primary |
| `artists[].tracks` | string | A | Empty = all tracks |
| `artists[].resource_url` | string | A | |
| `artists[].thumbnail_url` | string | S | |
| `extraartists[].id` | integer | A | |
| `extraartists[].name` | string | A | |
| `extraartists[].anv` | string | A | |
| `extraartists[].join` | string | A | |
| `extraartists[].role` | string | A | Always populated |
| `extraartists[].tracks` | string | A | |
| `extraartists[].resource_url` | string | A | |
| `labels[].id` | integer | A | |
| `labels[].name` | string | A | |
| `labels[].catno` | string | A | May be empty |
| `labels[].entity_type` | string | A | Numeric string |
| `labels[].entity_type_name` | string | A | |
| `labels[].resource_url` | string | A | |
| `labels[].thumbnail_url` | string | S | |
| `formats[].name` | string | A | |
| `formats[].qty` | string | A | |
| `formats[].text` | string | S | |
| `formats[].descriptions` | array[string] | S | |
| `genres` | array[string] | S | |
| `styles` | array[string] | S | May be empty array |
| `tracklist[].position` | string | A | |
| `tracklist[].type_` | string | A | |
| `tracklist[].title` | string | A | |
| `tracklist[].duration` | string | A | May be empty |
| `tracklist[].artists` | array | S | Per-track credits |
| `tracklist[].extraartists` | array | S | Per-track credits |
| `images[].type` | string | A | primary or secondary |
| `images[].uri` | string | A | Full-size URL |
| `images[].resource_url` | string | A | Same as uri |
| `images[].uri150` | string | A | 150x150 URL |
| `images[].width` | integer | A | |
| `images[].height` | integer | A | |
| `videos[].uri` | string | A | YouTube URL |
| `videos[].title` | string | A | |
| `videos[].description` | string | A | |
| `videos[].duration` | integer | A | Seconds |
| `videos[].embed` | boolean | A | |
| `community.have` | integer | A | |
| `community.want` | integer | A | |
| `community.rating.count` | integer | A | |
| `community.rating.average` | float | A | |
| `community.submitter.username` | string | A | |
| `community.submitter.resource_url` | string | A | |
| `community.contributors[].username` | string | A | |
| `community.contributors[].resource_url` | string | A | |
| `community.data_quality` | string | A | Same as top-level |
| `community.status` | string | A | Same as top-level |
| `identifiers[].type` | string | A | |
| `identifiers[].value` | string | A | |
| `identifiers[].description` | string | S | |
| `series` | array | A | Empty array when not in series |
| `companies[].id` | integer | A | |
| `companies[].name` | string | A | |
| `companies[].catno` | string | A | May be empty |
| `companies[].entity_type` | string | A | |
| `companies[].entity_type_name` | string | A | |
| `companies[].resource_url` | string | A | |
| `companies[].thumbnail_url` | string | S | |

### Master Release

| JSON path | Type | Presence | Notes |
|---|---|---|---|
| `id` | integer | A | |
| `title` | string | A | |
| `year` | integer | A | |
| `data_quality` | string | A | |
| `uri` | string | A | |
| `resource_url` | string | A | |
| `versions_url` | string | A | |
| `main_release` | integer | A | |
| `main_release_url` | string | A | |
| `most_recent_release` | integer | A | |
| `most_recent_release_url` | string | A | |
| `num_for_sale` | integer | A | |
| `lowest_price` | float | A | |
| `images` | array | S | |
| `genres` | array | A | |
| `styles` | array | A | |
| `tracklist` | array | A | |
| `artists` | array | A | |
| `videos` | array | S | |

### Artist

| JSON path | Type | Presence | Notes |
|---|---|---|---|
| `id` | integer | A | |
| `name` | string | A | |
| `realname` | string | S | |
| `profile` | string | A | May be empty |
| `data_quality` | string | A | |
| `uri` | string | A | |
| `resource_url` | string | A | |
| `releases_url` | string | A | |
| `urls` | array[string] | S | |
| `namevariations` | array[string] | S | |
| `aliases` | array[object] | S | |
| `groups` | array[object] | S | |
| `members` | array[object] | S | |
| `images` | array | S | |

### Label

| JSON path | Type | Presence | Notes |
|---|---|---|---|
| `id` | integer | A | |
| `name` | string | A | |
| `profile` | string | A | May be empty |
| `contact_info` | string | S | May be empty |
| `data_quality` | string | A | |
| `uri` | string | A | |
| `resource_url` | string | A | |
| `releases_url` | string | A | |
| `urls` | array[string] | S | |
| `sublabels` | array[object] | S | Empty array when none |
| `parent_label` | object | S | |
| `images` | array | S | |

---

## Full Lookup Flow

Step-by-step process for matching a DJ track to Discogs. No code.

### Step 1: Prepare search terms

From file metadata, collect whatever is available:
- Artist name (from tags or AcoustID/MusicBrainz)
- Track/release title
- Catalogue number (if visible on the record or in tags)
- Barcode (from tags or physical inspection)
- Label name
- Year

Priority: catno > barcode > artist+title. Catalogue number and barcode are the most
reliable identifiers because they are unique. Artist+title is fuzzy.

### Step 2: Execute search

**If catno is known:**
```
GET /database/search?catno={catno}&type=release
```
Also add `artist={artist}` to narrow results if multiple releases share the catno.

**If barcode is known:**
```
GET /database/search?barcode={barcode}&type=release
```

**If only artist+title known:**
```
GET /database/search?artist={artist}&release_title={title}&type=release
```
Or use a combined `q` parameter:
```
GET /database/search?q={artist}+{title}&type=release
```

Adding `format=Vinyl`, `style=Techno`, or `year={year}` as additional filters
reduces noise. Search is unauthenticated at 25 req/min; authenticated at 60.

### Step 3: Select the best result

If one result: proceed to Step 4.

If multiple results: evaluate candidates using:
1. **Catno match** — exact match = high confidence
2. **Artist match** — exact name match = high confidence
3. **Year match** — within expected range
4. **Format match** — prefer vinyl 12" for DJ library
5. **Country match** — if known from tags or record label
6. **`community.have` count** — higher `have` means better-documented release;
   use as tiebreaker, not primary signal
7. **`data_quality`** — prefer `"Correct"` or `"Complete and Correct"` over
   `"Needs Vote"`

### Step 4: Fetch the full release

```
GET /releases/{id}
```

Extract from the full release response:
- `labels[].name` and `labels[].catno` — the primary label and catalogue number
- `year` — release year
- `country` — release country
- `formats[].descriptions` — format details (12", LP, Promo, White Label etc.)
- `genres` and `styles` — genre/style tags
- `extraartists` — producers, remixers (check `role` field)
- `tracklist` — track positions and titles
- `identifiers` — barcodes and matrix numbers
- `community.have`, `community.want` — popularity signals
- `data_quality` — quality signal

### Step 5: Optionally fetch the Master Release

Fetch master when:
- You want to find other pressings of the same recording (to detect duplicates
  or find a better-documented version)
- You want release-level metadata that is common across all pressings (e.g. year
  of original release vs. year of this specific pressing)
- `master_id` is non-zero in the release response

```
GET /masters/{master_id}
GET /masters/{master_id}/versions
```

The master `year` is the year of the first release, which may be earlier than the
specific pressing's `year`.

Skip master fetch if the release has `master_id = 0` (no master assigned).

### Step 6: Optionally fetch the Label

Fetch label when:
- You want the label's parent company or sublabel structure
- You want the label's profile/history text
- The `labels[].catno` in the release response is empty or you want to verify

```
GET /labels/{label_id}
```

For most use cases in Crate (label name + catno), the full label fetch is not
necessary — these fields are already in the release response.

### Step 7: Handle zero results

If search returns `"items": 0`:
- Try alternative search terms (e.g. catno only, then artist+title only)
- Try searching without type filter to see if there are masters or other entity types
- The release may not be in Discogs (common for: true white labels, private
  pressings, DJ edits, very small runs)
- Log as `discogs_match = None` and proceed without Discogs data

### Step 8: Handle multiple plausible results

If search returns multiple results and confidence is low:
- Do not auto-select if catno/barcode match fails
- Score candidates and pick the highest-scoring match only if the margin is
  clear (e.g. score > 0.8)
- Otherwise: store the top candidate with a `discogs_confidence = "low"` flag
  for later manual review or skip and treat as no match

### Step 9: Handle white labels and promos with no match

True white labels (no label text, no catno, no barcode) will not be in Discogs.
Some will have a "White Label" entry if a collector added them. Approach:
- Search by artist if known (from AcoustID/MusicBrainz)
- If no match, log `discogs_match = None`
- Do not attempt to match on title alone for DJ edits/bootlegs — too much risk
  of false positives

---

## Coverage for Electronic Music

**Baseline:** Discogs originated as an electronic music database. Its coverage for
electronic music is widely considered superior to MusicBrainz and most other sources.

**Commercial techno/house 12" from major electronic labels:**
Coverage is very high. Well-documented labels (Axis, Purpose Maker, Tresor, R&S,
Warp, etc.) have extensive entries including multiple pressings of each release.
Catalogue numbers are almost always present.

**White label vinyl:**
Coverage varies widely. Some white labels have entries (especially if they were
later given a proper release or are collector items). Anonymous true white labels
(no markings at all) may not have entries. Confirmed from Discogs forums: white
labels can be submitted but require the submitter to have the physical copy.

**Promotional releases:**
Promos with catalogue numbers are generally in Discogs, tagged with `"Promo"` in
the `descriptions` array. Advance promos with different catalogue numbers than the
retail release may have separate entries. Some promos are entered as versions under
the retail master.

**Bootlegs and unofficial releases:**
Discogs allows bootleg submissions. They are not removed simply for being bootleg.
Coverage is inconsistent — depends on whether a collector submitted the item.

**DJ edits and re-edits:**
Generally absent unless a well-known DJ edit has been pressed as a formal release
(rare). Most DJ edits circulate as digital files or dubplates and are not in Discogs.

**Digital-only releases:**
Covered. The `format.name = "File"` format type covers digital releases. Coverage
for digital-only electronic music releases is good for established labels, weaker
for Bandcamp-only or self-released material.

**Old vinyl (1980s–1990s):**
Coverage for well-known 1980s–1990s electronic releases (Chicago house, Detroit
techno, UK rave, European trance) is good. Obscure regional releases from this era
may have gaps, but many have been submitted by collectors.

**Small/obscure labels:**
Coverage depends entirely on community interest. A small German techno label from
1994 with 10 releases may be fully documented if it has a dedicated collector
community, or may be absent. Discogs' strict requirements (physical copy in hand)
help ensure accuracy for what is there, but doesn't help with gaps.

**Match rate estimate for DJ library:**
Not published officially. Based on the above:
- Mainstream electronic labels: 70–90% expected match rate
- White labels / promos / dubplates: 20–50% expected match rate
- DJ edits / unofficial: less than 10% expected match rate
- Overall for a typical techno/house DJ library: estimate 50–75% match rate

**These are estimates, not published figures. Validate on real tracks in Phase 2.**

---

## Data Quality Signals

### `data_quality` field

Present on release, master, artist, and label objects at the top level, and also
within `community.data_quality` on releases.

| Value | Meaning |
|---|---|
| `"Complete and Correct"` | Above minimum requirements. Includes scans, full credits, all identifying numbers. Highest quality vote. |
| `"Correct"` | Contains correct information meeting minimum database standards. |
| `"Needs Vote"` | Submission has not yet been reviewed/voted on. Default for new submissions. Most common value. |
| `"Needs Minor Changes"` | Entry has been reviewed but requires minor corrections. |
| `"Needs Major Changes"` | Entry has significant errors or missing information. |
| `"Entirely Incorrect"` | Data is wrong, vandalized, or so incomplete it cannot be validated. An abuse report should be filed. |

For the Crate import pipeline, treat `"Complete and Correct"` and `"Correct"` as
reliable data. Treat `"Needs Vote"` as probably OK but potentially incomplete.
Treat `"Needs Major Changes"`, `"Entirely Incorrect"` with caution or skip.

### `status` field

Confirmed from live data: `"Accepted"` is the only observed value for publicly
accessible releases. Other possible values referenced in community discussions:

| Value | Meaning |
|---|---|
| `"Accepted"` | Release is live and publicly visible in the database |
| `"Draft"` | Not yet submitted for review (not publicly accessible via API) |
| `"Deleted"` | Removed from the database (not publicly accessible) |

Only `"Accepted"` releases are returned by the API in normal operation.

### Community Signals

| Field | Signal interpretation |
|---|---|
| `community.have` | Number of users who own this release. High = common, well-documented release. |
| `community.want` | Number of users who want this release. High want + low have = rare/desirable. |
| `community.rating.average` | Average user rating. Scale appears to be 1–5 based on observed data. |
| `community.rating.count` | Number of ratings. Low count = rating less reliable. |

Community `have` and `want` can help disambiguate when multiple releases match:
prefer the release with higher `have` as the "canonical" version.

---

## Pagination Reference

### Pagination Object

```json
{
  "pagination": {
    "page": 1,
    "pages": 10,
    "per_page": 50,
    "items": 472,
    "urls": {
      "first": "https://api.discogs.com/...?page=1",
      "last": "https://api.discogs.com/...?page=10",
      "prev": "https://api.discogs.com/...?page=0",
      "next": "https://api.discogs.com/...?page=2"
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `page` | integer | Current page (1-based) |
| `pages` | integer | Total number of pages |
| `per_page` | integer | Items per page |
| `items` | integer | Total number of matching items |
| `urls.first` | string | URL of first page (absent on page 1) |
| `urls.last` | string | URL of last page (absent on last page) |
| `urls.prev` | string | URL of previous page (absent on page 1) |
| `urls.next` | string | URL of next page (absent on last page) |

**When `urls` is an empty object `{}`:** zero results or single page.

**Maximum `per_page`:** 100. Confirmed from live testing: requesting 500 returns 100.
The default is 50.

**Maximum accessible pages:** For search results, the API appears to allow up to
10,000 pages of results (observed: `"pages": 5000` for style=Techno with per_page=2,
giving 10,000 items accessible). For other user inventories the limit is 100 pages.

---

## Installation

```
uv add python3-discogs-client
```

Or with pip:
```
pip install python3-discogs-client
```

**Minimal authentication verification script:**

```python
import discogs_client

# Replace with your actual token
d = discogs_client.Client(
    'CrateApp/0.1 (your@email.com)',
    user_token='YOUR_TOKEN_HERE'
)

me = d.identity()
print(f"Authenticated as: {me.username}")
print(f"Rate limit: 60 req/min")

# Test a release fetch
release = d.release(249504)
print(f"Release: {release.title}")
print(f"Labels: {[l.name for l in release.labels]}")
```

**Unauthenticated test (no token required, 25 req/min):**

```python
import discogs_client

d = discogs_client.Client('CrateApp/0.1 (your@email.com)')

release = d.release(249504)
print(release.title)
```

---

## Open Questions

1. **Search authentication requirement:** Live testing on 2026-04-04 showed search
   working without authentication. Official docs state authentication is required
   (since August 2015). Clarify whether unauthenticated search is truly permitted
   or was a temporary lapse. Always use authenticated for production.

2. **`status` values beyond `"Accepted"`:** Only `"Accepted"` was observed in live
   data. `"Draft"` and `"Deleted"` are referenced in community discussions but not
   confirmed from the API.

3. **Match rate for DJ library:** No published data. Estimated 50–75% overall for
   a techno/house library. Validate in Phase 2 against 50+ real tracks.

4. **Image 403 errors:** Some community reports mention 403 errors fetching images
   programmatically. Not reproduced in testing. Clarify whether image URLs require
   authentication or have hotlink restrictions before implementing image downloading.

5. **`data_quality` values:** Five values are documented (`"Complete and Correct"`,
   `"Correct"`, `"Needs Vote"`, `"Needs Minor Changes"`, `"Needs Major Changes"`,
   `"Entirely Incorrect"`). Only `"Needs Vote"` and `"Correct"` were observed in
   live data. Confirm all six values exist in practice.

6. **Complete Electronic styles list:** The list in this document is not guaranteed
   to be exhaustive. For a complete canonical list, parse the Discogs database dump
   or the submission form's dropdown. Relevant for building a style filter in the
   import pipeline.

7. **`community.rating` scale:** The observed values suggest a 1–5 scale but this is
   not confirmed in official documentation.

8. **`master_id = 0` in search results vs. absent in release endpoint:**
   Confirmed `master_id: 0` in search results when no master exists. Needs
   verification that `master_id` is absent (not 0) in full release responses.

9. **Rate of API changes:** Discogs changed the search authentication requirement
   in August 2015. Subsequent changes are documented in the forum API Announcements
   thread. Monitor https://www.discogs.com/forum/thread/521520689469733cfcfd2089
   for future changes.

10. **`per_page` limit for non-search endpoints:** Confirmed 100 for search. Not
    explicitly confirmed for release, master, artist, label sub-endpoints (versions,
    releases). Likely the same but not verified.
