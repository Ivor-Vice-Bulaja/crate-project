# Task: Research iTunes Search API as a Data Source

## Context

Read CLAUDE.md before starting. This task is Phase 1 research — no code is written here.
The goal is to produce a complete, accurate reference document that will be used to
finalise the database schema and the import pipeline in Phase 2.

Crate is a local DJ library application for techno and house DJs. The import pipeline
enriches each track with metadata from multiple sources. The iTunes Search API is a
candidate for returning track title, artist, album, year, genre, and artwork — all
without authentication. We need to know exactly what the API returns and how reliable
it is for electronic music before designing anything around it.

**Do not rely on prior knowledge about the iTunes Search API. Research it fresh from
the source.** The authoritative sources are:
- iTunes Search API documentation: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html
- iTunes Search API reference (search and lookup endpoints): https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html
- iTunes lookup endpoint: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/LookupExamples.html
- Any supplementary Apple developer docs linked from those pages

---

## What to research

### 1. What the iTunes Search API is

Before diving into request parameters, establish:
- What the iTunes Search API actually is — what it covers, who can use it, what data
  it draws from (Apple Music catalogue vs iTunes Store vs both)
- Whether it requires authentication — API keys, OAuth, anything
- Whether it is the same as the Apple Music API or a separate older service
- What the difference is between the search endpoint and the lookup endpoint
- Whether there is a Python library that wraps it, or if raw HTTP calls are standard
- What format the response is in (JSON assumed — confirm)

### 2. The search endpoint

Document the search endpoint exhaustively:

**Request parameters**
- Base URL and endpoint path
- All query parameters — name, type, allowed values, whether required or optional
- The `term` parameter — how search terms are handled, whether ISRC or UPC can be
  used as a term
- The `media` and `entity` parameters — what values are valid for music track lookups
- The `country` parameter — what it does, whether it affects result availability,
  what the default is
- The `limit` parameter — maximum allowed, default value
- The `lang` parameter — what it controls
- Any other parameters documented

**Response format**
- Exact JSON structure — every field at every level of nesting
- The `resultCount` field — what it contains
- The `results` array — what each element looks like for a track
- Every field in a track result object: name, type, example value, and meaning
- Which fields are always present vs sometimes absent
- What a zero-results response looks like
- Whether the API signals errors via HTTP status codes, response body fields, or both

**Rate limits**
- Whether rate limits are documented — exact numbers if available
- What happens when the limit is exceeded — HTTP status, response body
- Whether there is an undocumented practical limit based on community knowledge
  (note clearly if this is not from official docs)
- Whether there are per-IP, per-key, or per-app limits

### 3. The lookup endpoint

The lookup endpoint is distinct from search — it fetches a specific item by ID.

- Base URL and endpoint path for the lookup endpoint
- What IDs can be used — iTunes track ID (`trackId`), UPC, ISRC, Apple Music ID
- Exact request parameters
- Whether ISRC lookup is supported — this is critical for cross-referencing with
  MusicBrainz data
- Whether UPC/barcode lookup is supported
- Response format — same as search, or different fields?
- What a not-found lookup returns

### 4. Field inventory for a music track result

This is the most important section. Produce a complete table of every field returned
in a music track result from both the search and lookup endpoints.

For each field document:
- Field name (exact JSON key)
- Data type and example value
- Always/sometimes/rarely present
- What it represents — precise, not assumed
- Any known quality issues for electronic music

Pay particular attention to:
- `trackId` — is this stable over time?
- `artistId`, `collectionId` — what do these identify?
- `trackName`, `artistName`, `collectionName` — are these the release versions or
  normalised versions?
- `releaseDate` — what format, precision, what timezone
- `primaryGenreName` — how granular is it? Does it distinguish techno from house?
  Does it have sub-genres?
- `trackTimeMillis` — units confirmed?
- `artworkUrl100` — is this a template? Can larger sizes be requested?
- `isrc` — is this field present? This would allow cross-referencing with MusicBrainz
- `country` — what does this represent in the result?
- `wrapperType`, `kind` — what are these?
- Any fields not on the above list that appear in real responses

### 5. Coverage for electronic music

This is critical for Crate. DJ libraries contain:
- Commercial electronic releases on major labels (Warp, Kompakt, Drumcode)
- Releases on small independent techno/house labels
- White label vinyl rips
- Promos and unreleased tracks
- DJ edits and bootlegs
- Old vinyl from the 1990s and early 2000s

Research what is actually known about iTunes Search API coverage for these cases:
- Does Apple Music have strong coverage for electronic music compared to Discogs or
  MusicBrainz?
- Are white labels, promos, and old vinyl typically in the Apple Music catalogue?
- Are release dates accurate for older electronic music?
- Are genre tags granular enough to distinguish techno from house?
- Is there any known data on match rates or catalogue completeness for electronic music?

Document what can be confirmed from sources. Do not speculate — if data is unavailable,
say so explicitly.

### 6. Using the API in Python

Document how to call the iTunes Search API from Python:
- Whether there is a maintained Python library (search PyPI for `itunes`, `apple-music`,
  `pyitunes`) — if so, document its functions, return types, and maintenance status
- If no good library exists, what a minimal `requests`-based implementation looks like
  conceptually (not code — describe the calls)
- How to search by artist + title to find a specific track
- How to look up by ISRC if supported
- How to handle pagination if results exceed the limit
- How to handle rate limiting — retry logic, backoff
- Timeout behaviour — what the API does by default, how to configure it

### 7. Comparison to other sources in the pipeline

After documenting the API, briefly compare the iTunes Search API to the other sources
already researched (AcoustID + MusicBrainz, Discogs — when researched):
- What does iTunes provide that MusicBrainz does not?
- What does MusicBrainz provide that iTunes does not?
- For which fields is iTunes likely more reliable than MusicBrainz for electronic music?
- Is iTunes additive to the pipeline, or largely redundant given the other sources?
- Is artwork URL the main unique value-add?

### 8. Failure modes and edge cases

Document what is known about:
- Searching for a track with a common title and no artist — how noisy are results?
- Tracks with multiple iTunes editions (remastered, extended, radio edit) — how to
  identify the correct version
- Tracks where `trackTimeMillis` disagrees with the actual audio file duration
- International availability — does `country=us` give the broadest coverage?
- Encoding of special characters in search terms
- HTTP errors — 400, 403, 429, 503 — what they mean and when they occur
- What the API returns for a lookup by an ID that no longer exists

---

## Output format

Write your findings as a single Markdown document saved to:

```
docs/research/itunes.md
```

Structure it as follows:

```
# iTunes Search API Research

## Sources
Links to every page consulted, so findings can be verified.

## What the iTunes Search API Is
Orientation: what it covers, authentication (or lack thereof), relationship to
Apple Music API, search vs lookup endpoints.

## Search Endpoint Reference
URL, all parameters, full response structure (every field), rate limits.

## Lookup Endpoint Reference
URL, supported ID types (especially ISRC), response structure, not-found behaviour.

## Field Inventory
Complete table of every field in a music track result — JSON key, type,
always/sometimes/rarely present, meaning, known quality issues.
Crate candidate fields cross-referenced at the end.

## Python Integration
Library options or raw HTTP approach. Searching by artist+title. ISRC lookup.
Rate limit handling.

## Coverage for Electronic Music
What is confirmed about Apple Music catalogue depth for techno, house, white labels,
old vinyl. Be explicit about what could not be confirmed.

## Comparison to Other Pipeline Sources
What iTunes adds vs MusicBrainz. Where each source is stronger.

## Failure Modes and Edge Cases
Ambiguous results, ID stability, duration mismatches, HTTP errors.

## Open Questions
Anything that cannot be confirmed from documentation alone and needs a real test
in Phase 2.
```

---

## Definition of done

- [ ] `docs/research/itunes.md` exists and is written from primary sources
- [ ] Every field in a track result is documented with its JSON key, type, and meaning
- [ ] The lookup endpoint is documented — especially whether ISRC lookup is supported
- [ ] Rate limits are documented (or explicitly noted as undocumented)
- [ ] Coverage for electronic music is assessed as accurately as sources allow
- [ ] Python integration approach is documented
- [ ] Comparison to MusicBrainz is included
- [ ] All sources are linked so findings can be verified
- [ ] Open questions are listed so they can be answered by real tests in Phase 2
