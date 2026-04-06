# CURRENT_STATE.md

> Update this file at the end of every session. Claude Code reads it at the start of the next session.

---

## Status

Status: in progress
Current phase: Phase 1 — research and data mapping
Last session: 2026-04-05

## What was done

- Implemented all four importers: tags.py, acoustid.py, discogs.py, cover_art.py
- Wrote test script: scripts/test_importers.py — runs all importers on N tracks, prints summary
- Tested all importers on 50 real tracks from SEP2025 folder (WSL2, fpcalc available)
- Documented findings in docs/research/ for all four sources
- Fixed bug in discogs.py: strategy was always reported as "none" on no-match
- Installed Python 3.11 in WSL2 via uv; WSL venv lives at .venv/bin/python

## Real-data findings (50 techno/house tracks)

**mutagen:** Zero errors. 100% coverage on title, artist, album, label, genre, BPM,
key, embedded art. Year 50%. Catalogue number 0% (Beatport does not write TXXX:CATALOGNUMBER).

**AcoustID + MusicBrainz:** 14% match rate. 86% no-match — mostly 2024–2025 releases
from small labels not yet in AcoustID/MusicBrainz. When it matches, data is clean.
One false match observed (fingerprint collision). Requires fpcalc — WSL2 only.

**Discogs:** 12% match rate, all driven by catno from AcoustID/MB. Artist+title searches
return 0 results for niche techno releases. Styles field ("Deep Techno", "Dub Techno", etc.)
is the valuable output when matches occur.

**Cover Art Archive:** 12% match (exactly tracks AcoustID hits). Zero errors.
Release-level art found for all matched tracks. Embedded art (100% from tags) is
the primary display source; CAA is a higher-res supplement.

**Essentia (WSL2, 10 tracks, no ML, no pitch):** Zero errors. 100% on all core algorithm
outputs: BPM (avg 137.4, range 123.8–144.3), key, loudness (avg -8.6 LUFS), spectral
centroid, sub-bass ratio, high-freq ratio, MFCC, bark bands, onsets, danceability, tuning.
~14s/track reading from NTFS via /mnt/c/. ML outputs all None (no model files yet).
Fixed: `numpy<2` constraint added to pyproject.toml (essentia uses removed numpy.core API).

## Next action

Phase 1 research remaining:
- [ ] Map all source outputs into a single field inventory (side-by-side comparison)
- [ ] Finalise database schema based on confirmed field inventory
- [ ] Download Essentia ML model files and re-run to validate ML outputs
- [ ] Consider adding label+title Discogs search strategy (tag_label is 100%; would
      improve Discogs match rate for tracks where AcoustID fails)

## Open questions

- Should the importer add a label+title Discogs search step using tag_label?
  Currently catno from AcoustID is the only path to Discogs for this library type.
- How to handle AcoustID false matches? Artist name similarity check between
  tag_artist and MB artist would catch the case observed (Psychedelic Rock collision).

## Blockers

- Essentia ML models not yet downloaded (model files needed in ./models/).
- Running importers on Windows requires WSL2 (fpcalc + essentia are Linux-only).
