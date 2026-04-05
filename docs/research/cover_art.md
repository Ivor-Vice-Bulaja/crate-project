# Cover Art Archive — Research

Tested: 2026-04-05
Sample: 50 MP3 tracks from a techno/house DJ library (SEP2025 folder)
Script: `scripts/test_importers.py` (WSL2)

---

## What the Cover Art Archive returns

The CAA is a public API built on top of MusicBrainz. No authentication required.

**Lookup:** `GET https://coverartarchive.org/release/{mbid}/front-{size}`
or `GET https://coverartarchive.org/release-group/{mbid}/front-{size}`

Returns a **307 redirect** to the actual image on archive.org if art exists,
or **404** if not. We store the canonical CAA URL (not the archive.org redirect
target) because archive.org paths can change if MBIDs are merged.

**Thumbnail sizes:** 250, 500, or 1200 (pixels wide). Default: 500.

---

## Importer output fields

```
cover_art_url               str | None  — canonical CAA URL (follows 307 at display time)
cover_art_source            str | None  — "release" or "release_group"
cover_art_lookup_timestamp  str         — ISO 8601
cover_art_error             str         — only present on network or unexpected failure
```

---

## Lookup strategy (two-step fallback)

1. **Release-level:** `GET /release/{mb_release_id}/front-{size}`
   - Skipped if `mb_has_front_art = False` (pre-check from MB release lookup)
2. **Release-group fallback:** `GET /release-group/{mb_release_group_id}/front-{size}`
   - Only tried if release-level returns 404 or errors

Both MBIDs come from the AcoustID/MusicBrainz pipeline. If neither is available,
returns `cover_art_url = None` immediately without making any network call.

---

## Match rate — 50-track sample

| Metric | Count | Rate |
|---|---|---|
| Network errors | 0 | 0% |
| Cover art found | 6 | 12% |
| Source: release | 6 | 12% |
| Source: release-group | 0 | 0% |

**The 6 matches are exactly the same tracks that AcoustID matched.** CAA coverage is
fully dependent on MB data being available. For the 44 tracks where AcoustID returned
no match, there were no MB IDs to look up so no CAA call was made.

All 6 successful lookups resolved at the release level — the release-group fallback
was not needed for any track in this sample.

---

## Key findings

**CAA is free and reliable when MB data exists.** Zero network errors in 50 tracks,
clean 307 responses on all matched releases.

**Coverage tracks AcoustID match rate exactly.** If AcoustID can't identify the track,
there is no cover art from CAA. Embedded art in the file (100% coverage from tags)
should be used as the primary display source, with CAA as a higher-resolution supplement.

**Release-level art is preferred.** The `mb_has_front_art` flag from the MB release
lookup (stored as `acoustid.mb_has_front_art`) allows the importer to skip the release-level
call when it's known to be absent, saving one HTTP round trip.

**503 retry is implemented.** The importer retries once with a 1s delay on HTTP 503.
Not encountered in testing but CAA is known to occasionally serve 503 under load.

---

## Dependencies

Requires MB IDs from the AcoustID pipeline:
- `mb_release_id` — for release-level lookup
- `mb_release_group_id` — for release-group fallback
- `mb_has_front_art` — optional pre-check to skip a call

CAA is called after AcoustID/MB in the pipeline.
