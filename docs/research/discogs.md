# Discogs API — Research

Tested: 2026-04-05
Sample: 50 MP3 tracks from a techno/house DJ library (SEP2025 folder)
Script: `scripts/test_importers.py` (WSL2)

---

## What the Discogs API returns

### Release object (from `client.release(release_id)`)

```
id                    int     — Discogs release ID
title                 str     — release title (format: "Artist - Title")
year                  int     — release year
country               str     — country of release
released              str     — full release date string (e.g. "2025-02-14")
released_formatted    str     — human-readable (e.g. "14 Feb 2025")
status                str     — "Official", "Accepted", etc.
data_quality          str     — "Correct", "Complete and Correct", "Needs Vote", etc.
artists_sort          str     — sortable artist string
notes                 str     — release notes; often long HTML-ish text
num_for_sale          int     — current marketplace listings
lowest_price          float   — lowest current sale price (EUR/USD)
uri                   str     — Discogs URL for the release
master_url            str     — URL to master release (if exists)
master_id             int     — Discogs master release ID (0 → None in our importer)
```

### Label information

```
labels[0].id              int
labels[0].name            str     — label name
labels[0].catno           str     — catalogue number (empty string → stored as None)
labels[0].entity_type_name str   — "Label", "Series", etc.
```

Multiple labels are stored as JSON in `discogs_labels_raw`.

### Artists and extra artists

```
artists[].name            str     — release artists (JSON array stored as string)
extraartists[].name       str     — producers, remixers, etc.
extraartists[].role       str     — e.g. "Producer", "Remix", "Written-By"
```

Producers and remixers are extracted into separate JSON arrays (`discogs_producers`,
`discogs_remixers`) using role string matching. Full list in `discogs_extraartists_raw`.

### Genres and styles

```
genres      JSON array  — broad genre (e.g. ["Electronic"])
styles      JSON array  — specific styles (e.g. ["Techno", "Dub Techno", "Deep Techno"])
```

Styles are the useful field for a DJ library — genres are too broad. Both are stored as
JSON strings.

### Format

```
formats[].name          str     — "Vinyl", "CD", "File", "Cassette", etc.
formats[].descriptions  list    — e.g. ["12\"", "33 ⅓ RPM", "EP"]
```

Stored as JSON arrays: `discogs_format_names`, `discogs_format_descs`.

### Tracklist

```
tracklist[].position    str     — e.g. "A1", "B2"
tracklist[].title       str
tracklist[].duration    str     — e.g. "6:42"
tracklist[].type_       str     — "track" or "heading" (headings excluded from output)
```

Stored as JSON in `discogs_tracklist`.

### Identifiers

```
identifiers type="Barcode"         → stored in discogs_barcodes (JSON array)
identifiers type="Matrix / Runout" → stored in discogs_matrix_numbers (JSON array)
```

### Community data

```
community.have          int     — how many users own this release
community.want          int     — how many users want it
community.rating.average float  — average community rating
community.rating.count  int     — number of ratings
```

### Master release (optional, fetch_master=False by default)

```
master.year                  int  — year of first release in this master group
master.most_recent_release   int  — ID of most recent release in the master group
```

---

## Search strategy

The importer tries three strategies in order, stopping at the first that returns results:

1. **catno** — `client.search(catno=catno, type="release")` — most precise, requires catno
2. **barcode** — `client.search(barcode=barcode, type="release")` — exact match
3. **artist + title** — `client.search(artist=..., release_title=..., type="release")` with
   optional vinyl filter

Candidate scoring (higher = better):
- catno exact match (case-insensitive): +3.0
- artist name in result title: +2.0
- exact year match: +1.0; within 1 year: +0.5
- Vinyl format: +1.0; 12": +0.5
- data_quality Correct/Complete: +0.5
- community.have > 100: +0.25

Confidence thresholds: score ≥ 3.0 → "high"; score ≥ 1.0 → "low"; below → no match.

---

## Match rate — 50-track sample

| Metric | Count | Rate |
|---|---|---|
| Errors | 0 | 0% |
| High confidence match | 6 | 12% |
| Low confidence match | 0 | 0% |
| No match | 44 | 88% |

Search strategies used across 50 tracks:
- `catno`: 6 tracks — all from catalogue numbers supplied by the AcoustID/MB pipeline
- `artist_title`: 44 tracks — all returned 0 Discogs results

**The 6 catno matches are exactly the same tracks that AcoustID matched.** The catno came
from MusicBrainz, not from file tags (tag catno = 0%). On those 6, label/catno/year/styles
all came through correctly and matched MB data exactly.

**The 44 artist+title searches all returned 0 results.** These are 2024–2025 releases from
small techno/house labels that are either not on Discogs yet or not indexed under the exact
artist/title string in the tag.

---

## Key findings

**catno is the only reliable search key for this library.** Artist+title returns nothing
for new niche techno releases. Catno from AcoustID/MB is what unlocks Discogs.

**tag_label is 100% but is not currently used as a search parameter.** Adding a label+title
search (step 3.5 in the strategy chain) using `tag_label` from mutagen could improve the match
rate for tracks where AcoustID fails but the label name is known. Not yet implemented.

**Styles are the valuable genre field.** When Discogs matches, `discogs_styles` returns
specific values like `["Techno"]`, `["Dub Techno"]`, `["Deep Techno"]` which are directly
useful for crate fill. `discogs_genres` is always `["Electronic"]` — too broad to use.

**Discogs is a fallback enricher, not a primary source.** Its value is label/catno/styles
on tracks where MusicBrainz is weak or absent. For a modern techno/house library, expect
~10–15% match rate unless catno data is available.

**No match rate for new releases:** Discogs catalogue for 2025 techno releases is sparse.
Coverage will improve over 6–12 months as community members add releases.

---

## Bug fixed (2026-04-05)

`_no_match_dict("none")` at step 4 always reported strategy `"none"` even when
`artist_title` had been tried. Fixed to `_no_match_dict(strategy)` in
[backend/importer/discogs.py](../../backend/importer/discogs.py).

---

## Importer output fields (complete list)

```
discogs_release_id          int | None
discogs_master_id           int | None
discogs_confidence          str     — "high", "low", or "none"
discogs_search_strategy     str     — "catno", "barcode", "artist_title", or "none"
discogs_url                 str | None
discogs_title               str | None
discogs_year                int | None
discogs_country             str | None
discogs_released            str | None
discogs_released_formatted  str | None
discogs_status              str | None
discogs_data_quality        str | None
discogs_notes               str | None
discogs_artists_sort        str | None
discogs_num_for_sale        int | None
discogs_lowest_price        float | None
discogs_label_id            int | None
discogs_label               str | None
discogs_catno               str | None
discogs_label_entity_type   str | None
discogs_artists             JSON str | None
discogs_genres              JSON str | None
discogs_styles              JSON str | None
discogs_format_names        JSON str | None
discogs_format_descs        JSON str | None
discogs_producers           JSON str | None
discogs_remixers            JSON str | None
discogs_extraartists_raw    JSON str | None
discogs_labels_raw          JSON str | None
discogs_tracklist           JSON str | None
discogs_barcodes            JSON str | None
discogs_matrix_numbers      JSON str | None
discogs_have                int | None
discogs_want                int | None
discogs_rating_avg          float | None
discogs_rating_count        int | None
discogs_master_year         int | None
discogs_master_most_recent_id int | None
discogs_lookup_timestamp    str (ISO 8601)
discogs_error               str     — only present on failure
```
