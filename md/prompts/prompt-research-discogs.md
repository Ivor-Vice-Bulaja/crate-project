# Task: Research Discogs as a Data Source

## Context

Read CLAUDE.md before starting. This task is Phase 1 research — no code is written here.
The goal is to produce a complete, accurate reference document that will be used to
finalise the database schema and the import pipeline in Phase 2.

Crate is a local DJ library application for techno and house DJs. Every track gets
enriched on import using multiple metadata sources. We have chosen Discogs as one of
those sources. We need to know exactly what Discogs returns — from first principles,
based on its actual documentation and APIs — before we design anything around it.

**Do not rely on prior knowledge about Discogs or its API. Research it fresh from
the source.** The authoritative sources are:
- Discogs API documentation: https://www.discogs.com/developers/
- Discogs API reference (full endpoint list): https://www.discogs.com/developers/#page:home,header:home-general-information
- discogs_client Python library: https://github.com/joalla/discogs_client
- discogs_client documentation: https://discogs-client.readthedocs.io/
- Discogs data model and database: https://www.discogs.com/developers/#page:database

**Do not pre-filter what you document based on what you think the project needs.**
The goal of this research is to produce a complete picture of every field the Discogs
API returns. What is useful for Crate will be decided after the research is complete,
not during it.

---

## What to research

### 1. What Discogs is — orientation

Before touching the API, establish:
- What Discogs is as a platform — what data it holds, who contributes it, how it is
  structured, what distinguishes it from MusicBrainz
- The Discogs data model at a high level: what entities exist (Release, Master Release,
  Artist, Label, Format, Track listing, etc.) and how they relate to each other
- The difference between a Release and a Master Release — this is a critical distinction
  for understanding what the API returns
- What "community data" means in Discogs — ratings, have/want lists, marketplace
- What data types Discogs is strongest on (e.g. physical formats, electronic music labels)
  and what it is known to be weak on
- Whether Discogs data is community-contributed and what that implies for reliability

### 2. Authentication and API access

Document the full authentication model:
- All authentication methods the API supports — OAuth 1.0a, personal access tokens,
  application-only, unauthenticated — what each one enables and disables
- The exact process for obtaining a personal access token (what is required, any cost)
- The exact process for OAuth 1.0a (when is this needed vs a token)
- What endpoints are accessible without authentication vs with authentication
- What additional data becomes available when authenticated vs unauthenticated
- Any terms of service restrictions on automated/programmatic access

### 3. Rate limits — exhaustive documentation

Document every rate limit that applies:
- Requests per minute — authenticated vs unauthenticated, exact numbers
- Whether rate limits differ by endpoint type
- What the API returns when a rate limit is exceeded — HTTP status code, response body
- Whether there are daily or monthly caps in addition to per-minute limits
- The `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used`, `X-Discogs-Ratelimit-Remaining`
  response headers — document each one and what it contains
- Any official guidance on how to handle rate limiting in an automated import pipeline
- Whether rate limits are per IP, per token, or per application

### 4. Database search endpoint — complete documentation

Go to the Discogs API search documentation and document the search endpoint exhaustively.

**Request**
- Full endpoint URL
- All query parameters — document every parameter including name, type, allowed values,
  whether optional or required, and what it filters on
- Parameters that are specific to music search: type, release_title, artist, track,
  label, genre, style, country, year, format, catno, barcode, title, query — for each,
  document exactly what field it searches against in Discogs data
- Pagination parameters — how results are paginated, max results per page, how to
  traverse pages
- What `type` values are valid (release, master, artist, label) and what each returns

**Response — search results**
- Full JSON structure of a search results response
- The pagination object — every field
- The `results` array — document every field on a search result object
- For `type=release` results specifically — every field returned at the search level
  (note: search results are summaries; the full release requires a separate lookup)
- What fields are present in search results vs only available on the full release endpoint
- Null/missing field behaviour — which fields are always present vs sometimes absent

**Match strategies**
- How to search by catalogue number (`catno`) — exact format, case sensitivity,
  partial matching behaviour
- How to search by barcode — what barcode formats are accepted
- How to search by artist + title — how the ranking/relevance works
- Whether search results are ranked by relevance or another criterion
- What a zero-results response looks like

### 5. Release endpoint — complete documentation

The release endpoint returns the full data for a single release by its Discogs ID.
Document it exhaustively.

**Request**
- Full endpoint URL structure
- Path parameters
- Any query parameters (currency for marketplace data, etc.)

**Response — every field**
Document every field in the release response object. Do not skip fields because they
seem unrelated to music metadata — document all of them:

- Top-level scalar fields: `id`, `status`, `title`, `year`, `country`, `notes`,
  `data_quality`, `master_id`, `master_url`, `uri`, `resource_url` — for each:
  type, value range/format, always/sometimes present
- `artists` array — every field on an artist object within a release
- `extraartists` array — every field, what "role" contains, how it differs from
  `artists`
- `labels` array — every field (name, catno, entity_type, entity_type_name, id, resource_url)
- `formats` array — every field (`name`, `qty`, `text`, `descriptions` array) —
  document all known `descriptions` values (Vinyl, 12", 33 ⅓ RPM, EP, etc.)
- `genres` array — what values appear here, how genres are defined in Discogs
- `styles` array — how styles differ from genres, what values appear for electronic music
- `tracklist` array — every field on a track object:
  - `position`, `type_`, `title`, `duration`
  - `artists` and `extraartists` at the track level (yes, these exist at track level too)
  - Any sub-tracks or index tracks — how nested tracklists work
- `images` array — every field, image types, URL structure
- `videos` array — every field
- `community` object — every field (have, want, rating average, rating count,
  contributors, data_quality, status)
- `identifiers` array — every field (`type`, `value`, `description`) — document all
  known identifier types (Barcode, Matrix, ASIN, etc.)
- `series` array — every field
- `companies` array — every field — how this differs from `labels`
- `thumb` — what this is

**Field reliability for electronic music releases**
After documenting every field, assess each for reliability specifically for:
- 12" vinyl singles (the dominant format for techno/house)
- White labels (no official release info)
- Promos
- Digital-only releases
- Old releases (pre-2000 electronic music)

### 6. Master Release endpoint — complete documentation

A Master Release groups all versions of the same recording. Document the endpoint fully.

**Request**
- Full endpoint URL structure
- Any query parameters

**Response — every field**
- Every top-level field on a master release object
- How `main_release` and `main_release_url` work — what they point to
- The `versions` sub-endpoint — what it returns, pagination, fields on each version
- How master release data differs from individual release data
- When a release has no master (common for white labels) — what the API returns

### 7. Artist endpoint — complete documentation

**Request**
- Full endpoint URL structure

**Response — every field**
- Every field on an artist object
- The `releases` sub-endpoint on an artist — what it returns

### 8. Label endpoint — complete documentation

**Request**
- Full endpoint URL structure

**Response — every field**
- Every field on a label object: `id`, `name`, `profile`, `contact_info`, `uri`,
  `urls`, `images`, `sublabels`, `parent_label`, `data_quality`, `resource_url`
- The `releases` sub-endpoint on a label — what it returns, how to paginate
- How sublabels work in Discogs — what `sublabels` and `parent_label` contain

### 9. discogs_client Python library — complete documentation

Go to https://github.com/joalla/discogs_client and https://discogs-client.readthedocs.io/
and document the library from its source and docs:

**Setup and authentication**
- How to initialise the client with a personal access token
- How to initialise with OAuth
- The `user_agent` parameter — what format is required

**All methods available on the client object**
Do not summarise — list every method. For each:
- Method name and signature
- What it queries (which API endpoint)
- Return type and structure
- Any parameters

**Search**
- The `client.search()` method — all parameters, return type
- How to iterate through paginated results
- The `Page` and `PaginatedList` objects — what methods they have

**Object types returned**
For each object type the library wraps (Release, MasterRelease, Artist, Label, Track,
etc.) document:
- All attributes accessible on the object
- Which attributes require an additional API call (lazy loading) vs are available
  immediately from a search result
- How lazy loading works — when does it trigger an API call

**Error handling**
- All exception types the library raises
- What triggers each exception
- How HTTP errors (404, 429, 5xx) are surfaced to the caller
- Whether the library has built-in rate limit handling or retry logic

**Known issues and limitations**
- Maintenance status of the library
- Any known bugs or missing features
- Python version compatibility
- Whether there is an alternative library worth considering

### 10. Image and media URLs

Document everything about images in the Discogs API:
- URL structure for release images
- Whether image URLs require authentication to access
- Whether images are hosted on Discogs CDN or elsewhere
- Any restrictions on downloading or caching images
- Image types available (`primary`, `secondary`) and their meaning

### 11. Genres and styles taxonomy

Document the Discogs genre and style taxonomy as it relates to electronic music:
- All top-level genres that exist in Discogs
- All styles that fall under the "Electronic" genre — enumerate them from the API docs
  or by querying the API
- How genres and styles are structured — is it strictly hierarchical?
- What style tags are commonly used for techno and house specifically
- Any known issues with genre/style tagging (inconsistency, missing tags for certain
  release types)

### 12. Format vocabulary

Document the `formats` field vocabulary:
- All known `name` values for the `formats` array (Vinyl, CD, Cassette, File, etc.)
- All known `descriptions` values — enumerate them (12", LP, EP, Single, 33 ⅓ RPM,
  45 RPM, Album, Compilation, Promo, White Label, etc.)
- How to determine from the format data whether a release is a 12" vinyl single vs LP
  vs digital vs CD

### 13. The full lookup flow for a track

Document the complete sequence of API calls needed to go from a track's known
metadata (artist name, title, possibly catalogue number or barcode) to a full set
of Discogs data. Write this as step-by-step, not code:

1. What to search with — which search parameters give the best match rate
2. How to select the best result from search results — what criteria to use
3. What to fetch on the full release — which endpoint, which fields
4. Whether to also fetch the Master Release — when and why
5. Whether to fetch the Label — when and why
6. How to handle a zero-results search
7. How to handle multiple plausible results (e.g. same track released on multiple labels)
8. How to handle releases with no match (white labels, promos, unreleased edits)

### 14. Field inventory

This section is the most important output for Crate's database design.

**Start from what the API actually returns — not from what we want.**

Produce a complete inventory of every field returned by:
- The search results endpoint (type=release)
- The full release endpoint
- The master release endpoint
- The artist endpoint (fields relevant to a track record)
- The label endpoint (fields relevant to a track record)

For each field in the inventory document:
- Field name and full JSON path
- Data type and value range or format
- Whether it is always present, sometimes present, or rarely present
- What it represents — be precise
- Any known quality issues, especially for electronic music

After completing the full inventory, note which fields map to these Crate candidates
as a secondary reference — but do not let this list constrain the inventory:
```
label, catalogue_number, release_year, genre, style, country, format,
artist_id, release_id, master_id, barcode, track_position, track_duration
```

If the API returns fields not on this list that could be useful for a DJ library,
call them out explicitly. If a field on this list does not exist or is unreliable,
say so directly.

### 15. Coverage for electronic music

This is critical for understanding how much Discogs can be relied on.

Research what is known about Discogs coverage for:
- Commercial techno and house 12" releases from major electronic labels
- White label vinyl (releases with no official label name)
- Promotional releases (promos sent to DJs, often with "Promo" or "Not For Sale" markings)
- Bootlegs and unofficial releases
- DJ edits and re-edits
- Digital-only releases
- Old vinyl from the 1980s–1990s
- Releases on small or obscure labels

For each category: document what is known from the Discogs community, forums,
or any published data. If nothing can be confirmed from sources, say so explicitly.
Do not speculate.

### 16. Data quality signals

Document what Discogs provides that allows an importer to assess the quality
of a match or the completeness of a release entry:
- The `data_quality` field — what values it can take and what each means
- The `community.data_quality` field — same
- The `community.have` and `community.want` fields — what high numbers imply
- The `status` field on a release — what values exist ("Accepted", "Draft", etc.)
- Any other signals available in the response that indicate how complete or reliable
  the entry is

### 17. Pagination

Document pagination fully:
- The `Pagination` object — every field (`page`, `pages`, `per_page`, `items`, `urls`)
- The `urls` sub-object — what `first`, `last`, `prev`, `next` contain
- Maximum `per_page` value
- How to request a specific page
- Whether the total item count is always accurate or sometimes estimated

### 18. Installation

Document the correct installation procedure:
- `discogs_client` — exact uv/pip install command and package name
- Any OS-level dependencies
- A minimal Python script that verifies authentication works and fetches one release
- Any known installation issues

---

## Output format

Write your findings as a single Markdown document saved to:

```
docs/research/discogs.md
```

Structure it as follows:

```
# Discogs Research

## Sources
Links to every page consulted, so findings can be verified.

## What Discogs Is
Orientation: platform, data model, entities, relationship to MusicBrainz.
Release vs Master Release distinction explained precisely.

## Authentication and API Access
All auth methods, token setup, what is accessible without auth.

## Rate Limits
All limits, headers, behaviour on exceed. Authenticated vs unauthenticated.

## Search Endpoint Reference
Full request parameters, full response structure, field inventory for search results.
Match strategies for catalogue number, barcode, artist+title.

## Release Endpoint Reference
Full response structure — every field at every nesting level.
Format vocabulary. Field reliability for electronic music.

## Master Release Endpoint Reference
Full response structure. Versions sub-endpoint.

## Artist Endpoint Reference
Full response structure.

## Label Endpoint Reference
Full response structure. Sublabels and parent labels.

## discogs_client Library Reference
All methods, return types, object attributes (lazy vs eager), error handling.

## Genres and Styles Taxonomy
Full taxonomy for the Electronic genre. Techno/house style tags.

## Format Vocabulary
All known format names and descriptions.

## Field Inventory
Complete table of every field returned across all relevant endpoints.
Source, JSON path, always/sometimes/rarely, known quality issues.
Crate candidate fields cross-referenced at the end.

## Full Lookup Flow
Step-by-step: known track metadata → search → select → fetch full release → fields.
All failure paths documented.

## Coverage for Electronic Music
What is confirmed about coverage for each release type.
Explicit about what could not be confirmed.

## Data Quality Signals
Every signal available to assess match quality or entry completeness.

## Pagination Reference
Full pagination object, URL fields, max page size.

## Installation
Step-by-step for Python 3.11 and uv.

## Open Questions
Anything that cannot be confirmed from documentation alone and needs
a real test on actual releases in Phase 2.
```

---

## Definition of done

- [ ] `docs/research/discogs.md` exists and is written from primary sources
- [ ] Every field returned by the search, release, master release, artist, and label
      endpoints is documented with its name, type, and meaning
- [ ] The field inventory covers every field returned, not just the Crate candidate list
- [ ] The full lookup flow documents every step including all failure paths
- [ ] Rate limits are documented with exact numbers and header names
- [ ] The genres/styles taxonomy for electronic music is enumerated, not summarised
- [ ] The format vocabulary is enumerated (all known names and descriptions)
- [ ] Coverage for electronic music documents what is confirmed vs unknown
- [ ] The discogs_client library reference covers all methods and object attributes
- [ ] Data quality signals are all documented with their possible values
- [ ] Installation instructions are specific to Python 3.11 and uv
- [ ] All sources are linked so findings can be verified
- [ ] Open questions are listed so they can be answered by running real tests in Phase 2
