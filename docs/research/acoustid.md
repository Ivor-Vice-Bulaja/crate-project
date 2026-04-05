# AcoustID + MusicBrainz — Research

Researched: 2026-04-03 (API field mapping)
Tested on real tracks: 2026-04-05
Sample: 50 MP3 tracks from a techno/house DJ library (SEP2025 folder)
Script: `scripts/test_importers.py` running in WSL2 (fpcalc required)

---

## What AcoustID returns

**AcoustID lookup** (`meta=recordings+releasegroups`) returns:

```
acoustid_id           str (UUID)   — AcoustID fingerprint identifier
acoustid_score        float 0–1    — fingerprint match confidence; no official threshold
acoustid_match        bool         — True if any result returned
mb_recording_id       str (UUID)   — MusicBrainz recording UUID; use for MB lookup
title                 str          — sometimes absent if not in MB
duration              int, SECONDS — sometimes absent
artists[].id          UUID
artists[].name        str
releasegroups[].id    UUID
releasegroups[].title str
releasegroups[].type  str          — "Album", "Single", "EP", etc.
```

No label, catalogue number, year, genre, ISRC, or BPM from AcoustID directly.

**MusicBrainz recording lookup** (`inc=artist-credits+releases+isrcs+tags`) returns:

```
id                               str (UUID)  — recording MBID
title                            str         — always present
length                           int, MS     — sometimes null
first-release-date               str         — "YYYY", "YYYY-MM", or "YYYY-MM-DD"; sometimes absent
video                            bool
disambiguation                   str
isrcs[]                          array of ISRC strings — often empty for electronic music
artist-credit[].name             credited name string
artist-credit[].joinphrase       join string (e.g. " feat. ", " & ")
artist-credit[].artist.id        UUID
artist-credit[].artist.name      canonical artist name
artist-credit[].artist.sort-name sort-order name
artist-credit[].artist.type      "Person", "Group", etc.
artist-credit[].artist.country   ISO 3166-1; sometimes absent
releases[].id                    release MBID
releases[].title                 release title
releases[].status                "Official", "Promotion", "Bootleg", "Pseudo-Release"
releases[].date                  string, partial dates possible; sometimes absent
releases[].country               ISO 3166-1; null for worldwide
releases[].barcode               string or null
releases[].release-events[].date all regional release dates
tags[].name / tags[].count       community tags — sparse for electronic music
genres[].name / genres[].count   not supported by musicbrainzngs 0.7.1; always []
```

**Label and catalogue number require a separate release lookup:**

```
GET /ws/2/release/{RELEASE_MBID}?inc=labels&fmt=json
→ label-info[].label.name        — label name
→ label-info[].catalog-number    — American spelling; not "catalogue"
→ cover-art-archive.front        — bool; True if front art exists in CAA
→ status                         — release status
→ date                           — release date
```

**Key unit difference:** AcoustID `duration` is in **seconds**; MusicBrainz `length` is in **milliseconds**.

---

## Match rate — 50-track sample

| Metric | Count | Rate |
|---|---|---|
| Lookup errors | 0 | 0% |
| AcoustID fingerprint match | 7 | 14% |
| Resolved to MB recording | 6 | 12% |
| Title, artist, label, year, catno | 6 | 12% |
| mb_has_front_art = True | 6 | 12% |

AcoustID score on matches: min=0.423, max=1.000, avg=0.914

**86% no-match rate** on this sample. Root cause: these are mostly 2024–2025 releases
from small techno/house labels. New releases take time to appear in AcoustID/MusicBrainz;
obscure labels are poorly covered.

This is consistent with the CLAUDE.md estimate of 30–60% no-match for a typical DJ library.
A library including older, more widely-known electronic releases would have higher coverage.

---

## False match observed

Track: `Alessandro (COL) - Parole Confuse` was matched to `Morly Grey — Peace Officer (2000)`,
a Psychedelic Rock release. The fingerprint collision produced a plausible AcoustID score.

**Implication:** acoustid_score alone is not sufficient to validate a match. Cross-checking
artist name similarity between the tag artist and the MB artist would catch this.
A score threshold of ~0.85 is a reasonable starting point for auto-accepting matches,
with lower scores flagged for review.

---

## fpcalc requirement

AcoustID fingerprinting requires the `fpcalc` binary (Chromaprint). On Windows:
- Native Python: **does not work** — fpcalc is not available
- WSL2: **works** — `sudo apt install libchromaprint-tools` installs fpcalc

The import pipeline must run in WSL2 or Linux. This is already noted in CLAUDE.md.

---

## Rate limits

- AcoustID: no published rate limit; the importer retries once on WebServiceError with 2s delay
- MusicBrainz: 1 req/s per their terms of service; enforced by `mb_rate_limit=True` (1s sleep)
- With `fetch_label=True`: 3 network calls per track (AcoustID + MB recording + MB release)
- Observed throughput: ~4.7s/track end-to-end (includes Discogs and CAA calls)

---

## Importer output fields

```
acoustid_id              str | None
acoustid_score           float | None
acoustid_match           bool
mb_recording_id          str | None
mb_release_id            str | None
mb_release_group_id      str | None
mb_release_group_type    str | None
mb_artist_id             str | None
title                    str | None
artist                   str | None
artist_sort_name         str | None
year                     int | None
mb_duration_s            float | None
isrc                     str | None
mb_release_title         str | None
release_status           str | None
release_country          str | None
label                    str | None
catalogue_number         str | None
mb_has_front_art         bool | None
genres                   list (always []; musicbrainzngs 0.7.1 does not support genre includes)
tags                     list[str] — MB community tags; sparse for electronic music
lookup_error             str       — only present on failure
```
