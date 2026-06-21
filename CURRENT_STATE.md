# CURRENT_STATE.md

> Update this file at the end of every session. Claude Code reads it at the start of the next session.

---

## Status

Status: in progress
Current phase: Phase 2 — Import pipeline (complete)
Last session: 2026-06-21

## What was done

**Session 2026-06-21 (embeddings + sqlite-vec)**
- Implemented `backend/importer/embeddings.py` — sentence-transformers text embedding
  - `build_text(row)` builds a natural-language description from all populated DB columns (artist, title, BPM, key, label, year, Discogs styles/genres, Essentia ML labels, mood scores, voice probability, MusicBrainz tags)
  - `embed_row(row, model_name)` encodes the text with sentence-transformers; model cached in-process
  - Model: `all-MiniLM-L6-v2` (384-dim, CPU-only, fast)
- Added `EmbeddingsConfig` to `backend/config.py` (model_name, enabled flag)
- Updated `backend/database.py`:
  - Migration 2 now creates both `vec_tracks` (1280-dim audio, Essentia) AND `vec_tracks_text` (384-dim text, sentence-transformers)
  - Added `_VEC_TEXT_AVAILABLE` module flag alongside `_VEC_AVAILABLE`
- Updated `backend/importer/pipeline.py` step 9 to write both vec tables:
  - `vec_tracks` — Essentia EffNet audio embedding, written only when Essentia ran
  - `vec_tracks_text` — sentence-transformers text embedding, written always when sqlite-vec available
- Added `sqlite-vec==0.1.9` to dependencies (`uv add sqlite-vec`)
- Fixed `backend/cli.py` `discover_files` — now skips any path with a dotfile component (`.venv`, `.git`, etc.) to prevent importing scipy test WAVs and other package files
- Added `backend/tests/test_importer/test_embeddings.py` — tests for `build_text` and `embed_row`

**End-to-end validation (2026-06-21):**
- Ran `crate-import --folder . --db ./crate.db` on project root (2 real tracks)
- Both tracks imported correctly; `vec_tracks_text` populated with 384-dim vectors
- sqlite-vec and sentence-transformers confirmed working together
- Essentia not run (not on `--extra analysis` in this session); `vec_tracks` remains empty until WSL2 + analysis extra

**Session 2026-04-19 (Essentia validation)**
- Installed Essentia in WSL venv via `uv sync --extra analysis` (essentia==2.1b6.dev1389, essentia-tensorflow==2.1b6.dev1389)
- Ran `analyse_track` on `Cevi - High Line.wav` — all standard algorithms succeeded, no errors
- Results: BPM 144.95, confidence 2.37/5.32, key F# minor (strength 0.374), integrated loudness -8.36 LUFS, loudness range 5.40 LU, dynamic complexity 3.06, spectral centroid 1589 Hz, sub-bass ratio 0.607, high-freq ratio 0.034, danceability 1.30, onset rate 5.68/s, tuning 438.5 Hz, 701 beat ticks, beat interval std 0.0114s (very tight)
- TensorFlow detected RTX 3070 GPU but CUDA libs not installed in WSL — ML models fall back to CPU (not blocking)
- ML model results: genre top-1 = Electronic/Techno, ml_danceability = 1.000, mood_party = 0.998, voice_probability = 0.145 (instrumental), all 5 embeddings returned (1280-dim EffNet + 512-dim track/artist/label/release)

**Session 2026-04-19 (pipeline)**
- Implemented `backend/importer/pipeline.py` — full import pipeline orchestrator
- Added `PipelineConfig` to `backend/config.py` — wraps all per-importer configs; creates Discogs client once per session in `__post_init__`
- Wrote 47 tests across three files; all pass

**Session 2026-04-19 (database schema)**
- Finalised and implemented full SQLite schema in `backend/database.py`
- Migration 1: `tracks` table (~180 columns)
- Migration 2: `vec_tracks` + `vec_tracks_text` virtual tables (sqlite-vec)
- Migration 3: indexes on tracks
- Migration 4: crate management tables

**Session 2026-04-17 (importer validation)**
- Ran full batch test: all 5 importers on 50 tracks from JUN2025 - HOUSE TRANCY
- Zero errors. iTunes 84%, Discogs 64%, AcoustID 36%, CAA 18%

## Phase 2 checklist

- [x] Validate Essentia on real track (WSL2)
- [x] Pipeline orchestration (`backend/importer/pipeline.py`) — 47/47 tests pass
- [x] `PipelineConfig` added to `backend/config.py`
- [x] SQLite schema + migrations (`backend/database.py`)
- [x] Essentia audio analysis wired into pipeline (step 3c)
- [x] `scripts/import_library.py` → moved to `backend/cli.py`, registered as `crate-import` entry point
- [x] Embeddings (`backend/importer/embeddings.py`) — sentence-transformers text embedding; sqlite-vec write in pipeline step 9

**Phase 2 is complete.**

## Next action

**Phase 3 — Backend API:**
- FastAPI setup (`backend/main.py`)
- `GET /tracks` endpoint with filter, sort, group params (`backend/api/tracks.py`)
- Basic crate CRUD (`backend/api/crates.py`)

## Real-data findings (50 tracks, JUN2025 HOUSE TRANCY)

**mutagen:** 100% title, artist, album, label, genre. 96% BPM/key. 90% year.
**iTunes (84%):** Best single source. Artwork URL is primary value-add.
**Discogs (64%):** label+title strategy is the workhorse. Best for styles/catno.
**AcoustID + MusicBrainz (36%):** Bonus where available; primary source for untagged files.
**Cover Art Archive (18%):** Gated on AcoustID. 75% hit rate when AcoustID succeeds.

## Known issues / notes

- iTunes can false-match on artist name when title doesn't match (observed: "Say Less" matched to "Break Theory (Mixed)" on same album). Confidence scoring accepted it due to artist match + close duration. Not blocking but worth a stricter title similarity check in future.
- Essentia ML models not yet downloaded to `./models/` (needed for genre/mood outputs on real tracks).
- All Essentia work requires WSL2: `wsl -e bash -c "cd /mnt/c/Users/bulaj/Desktop/crate-project && ..."`
- sqlite-vec 0.1.9 installed; vec_tracks_text confirmed working (384-dim, sentence-transformers all-MiniLM-L6-v2).

## Deferred

- [ ] Research Last.fm API
- [ ] Research Deezer API
- [ ] Spotify integration (Phase 5)
