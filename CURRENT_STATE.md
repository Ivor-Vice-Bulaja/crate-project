# CURRENT_STATE.md

> Update this file at the end of every session. Claude Code reads it at the start of the next session.

---

## Status

Status: in progress
Current phase: Phase 2 — Import pipeline
Last session: 2026-04-19

## What was done

**Session 2026-04-19 (Essentia validation)**
- Installed Essentia in WSL venv via `uv sync --extra analysis` (essentia==2.1b6.dev1389, essentia-tensorflow==2.1b6.dev1389)
- Ran `analyse_track` on `Cevi - High Line.wav` — all standard algorithms succeeded, no errors
- Results: BPM 144.95, confidence 2.37/5.32, key F# minor (strength 0.374), integrated loudness -8.36 LUFS, loudness range 5.40 LU, dynamic complexity 3.06, spectral centroid 1589 Hz, sub-bass ratio 0.607, high-freq ratio 0.034, danceability 1.30, onset rate 5.68/s, tuning 438.5 Hz, 701 beat ticks, beat interval std 0.0114s (very tight)
- TensorFlow detected RTX 3070 GPU but CUDA libs not installed in WSL — ML models fall back to CPU (not blocking; `run_ml_models=False` for now)
- Essentia validation complete. Phase 2 standard analysis confirmed working.

**Session 2026-04-19 (pipeline)**
- Implemented `backend/importer/pipeline.py` — full import pipeline orchestrator
- Added `PipelineConfig` to `backend/config.py` — wraps all per-importer configs; creates Discogs client once per session in `__post_init__`
- Created `backend/tests/fixtures/short.mp3` — minimal MP3 test fixture for integration tests
- Wrote 47 tests across three files; all pass:
  - `test_pipeline_skip.py` — hash/mtime change detection (7 tests)
  - `test_pipeline_merge.py` — `_build_db_row` column completeness, all resolved_* field priority chains (33 tests)
  - `test_pipeline_db.py` — real DB UPSERT, id preservation on re-import, crate membership survival, skip logic, error resilience (7 tests)
- WSL venv was rebuilt by uv during this session (old venv was Windows-only symlink artifact)

**Session 2026-04-19 (database schema)**
- Finalised and implemented full SQLite schema in `backend/database.py`
- Migration 1: `tracks` table (~180 columns)
- Migration 2: `vec_tracks` virtual table (sqlite-vec; skipped if unavailable)
- Migration 3: indexes on tracks
- Migration 4: crate management tables (crates, crate_tracks, crate_corrections)
- 9/10 tests pass (one minor test issue noted but not blocking)

**Session 2026-04-17 (importer validation)**
- Added iTunes importer to test_importers.py
- Ran full batch test: all 5 importers on 50 tracks from JUN2025 - HOUSE TRANCY
- Zero errors. iTunes 84%, Discogs 64%, AcoustID 36%, CAA 18%

## Pipeline implementation details (for next session reference)

`import_track(file_path, db, config)` execution order:
1. `_check_skip()` — mtime fast-path, then hash verify; returns None on hit
2. `_hash_file()` + `os.stat()` — MD5 hex digest + file size/mtime for INSERT
3. `read_tags(path)` — synchronous
4. `ThreadPoolExecutor(max_workers=3)`: AcoustID (90s timeout), iTunes (30s), Essentia (300s, WSL2 only)
5. `fetch_discogs_metadata()` — sequential, after executor exits; inputs from tags + acoustid
6. `fetch_cover_art()` — sequential, after executor exits; inputs from acoustid
7. `_build_db_row()` — explicit column mapping + resolved_* computation
8. UPSERT via `INSERT INTO tracks ... ON CONFLICT(file_path) DO UPDATE SET ...`
9. Essentia embedding → `DELETE + INSERT INTO vec_tracks` (gated on `_VEC_AVAILABLE`)

`import_tracks(paths, db, config, on_progress)` — batch loop; calls import_track per path.

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

## Next action

**Immediate (Phase 2 remaining):**
- [x] Validate Essentia on real track (WSL2) — confirmed working on Cevi - High Line.wav; all standard algorithms + all ML models successful
- ML model results: genre top-1 = Electronic/Techno, ml_danceability = 1.000, mood_party = 0.998, voice_probability = 0.145 (instrumental), all 5 embeddings returned (1280-dim EffNet + 512-dim track/artist/label/release)
- [x] Write `scripts/import_library.py` — complete; CLI with argparse, rglob discovery, move detection, tqdm progress, import/skip/error counters, summary report; plan at `md/plans/plan-import-library.md`
- [x] Tests for `import_library.py` — 10 tests in `backend/tests/test_importer/test_import_library.py`; covers discovery, move detection, dry-run, counters, config error, duration formatting
- [ ] Embeddings (`backend/importer/embeddings.py`) — sentence-transformers or Essentia EffNet; decision needed before implementation

**Deferred:**
- [ ] Research Last.fm API
- [ ] Research Deezer API

## Open questions

- Embedding source decision: use Essentia EffNet embedding (1280-dim) when available (WSL2),
  fall back to sentence-transformers when Essentia unavailable? Needs explicit decision before
  `embeddings.py` is implemented.
- False match detection for AcoustID: artist name similarity check between tag_artist and MB artist
  would catch fingerprint collisions observed in prior sessions.

## Blockers

- Essentia ML models not yet downloaded (needed in ./models/ for genre/mood outputs).
- All Essentia and AcoustID work requires WSL2.
  Run command prefix: `wsl -e bash -c "cd /mnt/c/Users/Gamer/code/crate-project && ..."`
