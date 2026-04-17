# CURRENT_STATE.md

> Update this file at the end of every session. Claude Code reads it at the start of the next session.

---

## Status

Status: in progress
Current phase: Phase 1 — research and data mapping / Phase 1.5 — importer implementations
Last session: 2026-04-17

## What was done

**Session 2026-04-17**
- Added iTunes importer to test_importers.py (it was missing despite the importer existing)
- Ran full batch test: all 5 importers on 50 tracks from JUN2025 - HOUSE TRANCY
- Results saved to scripts/output/importers_test_20260411T092838.json
- Updated CLAUDE.md and CURRENT_STATE.md to reflect current project state

**Prior sessions (to 2026-04-11)**
- Researched and implemented all 5 importers: tags.py, acoustid.py, discogs.py, cover_art.py, itunes.py
- Wrote test harness: scripts/test_importers.py
- Researched: Essentia, AcoustID/MusicBrainz, mutagen, iTunes Search API
- Installed Python 3.12 in WSL2 via uv; WSL venv at .venv/bin/python
- Fixed numpy<2 constraint for Essentia compatibility

## Real-data findings — 50 tracks from JUN2025 HOUSE TRANCY (2026-04-17)

Zero errors from any importer across all 50 tracks.

**mutagen:** 100% title, artist, album, label, genre. 96% BPM/key. 90% year. 98% embedded art.
0% catalogue number (not tagged by source). All MP3. No DJ software tags.

**iTunes (84% high-confidence):** Best single source. 86% artwork URL, release date, genre fill.
Genres too coarse ("Electronic"/"House"/"Dance") — confirmed useless for crate logic.
7/50 no-match: Gestalt/Glow Mid promo releases not on iTunes.

**Discogs (64% high-confidence):** label+title strategy is the workhorse (22/32 matches).
Does not require AcoustID — works from filename-parsed artist/title and tag_label.
64% fill on label, catno, genres, styles. Known data issue: GS027 catno attributed to
"Goldmine Soul Supply" instead of "Gestalt Records" in Discogs.

**AcoustID + MusicBrainz (36% match):** Confirms research estimate for indie/house library.
Of 18 fingerprint matches, 12 had full MB recording data. Avg AcoustID score 0.837.
AcoustID/MB is a bonus where available, not a primary source for this library type.

**Cover Art Archive (18%):** Gated on AcoustID. Of 12 tracks with MB recording IDs,
9 had CAA art (75%). Low overall rate is a consequence of AcoustID miss rate.

## Importer priority order (confirmed from real data)

For title/artist/artwork/date: iTunes → MusicBrainz → tags → filename
For label/catno/styles: Discogs → MusicBrainz → tags
For fingerprint identity: AcoustID → (no fallback)
For cover art: embedded tags → CAA (release) → CAA (release-group) → iTunes artwork URL

## Next action

Phase 1 research remaining:
- [ ] Research Discogs API formally — document exact field outputs in docs/research/discogs.md
- [ ] Research Last.fm API — scrobble data, tag schema, rate limits
- [ ] Research Deezer API — BPM, label, coverage for electronic music
- [ ] Map all confirmed source outputs into a single field inventory (side-by-side)
- [ ] Finalise database schema from field inventory

Phase 1.5 remaining:
- [ ] Validate Essentia on 50 real tracks (WSL2) — calibrate BPM, key, loudness, derived scores
  - Run: `wsl -e bash -c "cd /mnt/c/Users/Gamer/code/crate-project && .venv/bin/python scripts/test_importers.py --folder '/mnt/c/Users/Gamer/Desktop/Desktop Temp/JUN2025 - HOUSE TRANCY' --count 10 --no-acoustid --no-discogs --no-cover-art --no-itunes --essentia"`
  - ML models not yet downloaded — run without --essentia-ml first

## Open questions

- Should the pipeline use iTunes artist/title as the canonical display name when MB is absent?
  (84% match rate makes it the most reliable source for this library type)
- How to handle the Discogs catno mislabelling issue (GS027 = Goldmine Soul Supply vs Gestalt)?
  Probably not worth solving — it's a Discogs data quality problem, not a code problem.
- False match detection for AcoustID: artist name similarity check between tag_artist and
  MB artist would catch fingerprint collisions (Psychedelic Rock collision observed in prior session).

## Blockers

- Essentia ML models not yet downloaded (needed in ./models/ for genre/mood outputs).
- All Essentia and AcoustID work requires WSL2 (fpcalc + essentia are Linux-only).
  Run command prefix: `wsl -e bash -c "cd /mnt/c/Users/Gamer/code/crate-project && ..."`
