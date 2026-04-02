# Crate — Claude Code Project Brief

> Hand this file to Claude Code at the start of every session.
> Keep it updated as decisions are made and things get built.

---

## What is Crate

A smart music library application for DJs. The core idea: every track in the library gets
automatically analysed and classified, and the DJ defines collections (crates) in plain
language which the app populates and maintains using AI.

Target user: techno and house DJs with libraries of 5,000–20,000 tracks.

The app is a personal, local-first tool. No multi-user, no cloud sync in v1.

---

## The Two-Layer Architecture

**Layer 1 — Data (fully automatic, no user input)**
Every track gets analysed on import. The pipeline runs in the background and writes
structured audio features and metadata to a local SQLite database. The user never
touches this layer directly.

**Layer 2 — Crates (user-defined, AI-populated)**
The user writes a plain language description of a crate. The app reads the structured
data from Layer 1 and populates the crate automatically. Manual corrections feed back
into improving future fills.

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| Audio analysis | Essentia (Python) | MTG Barcelona, open source |
| Track identification | AcoustID + pyacoustid | Free, fingerprint-based |
| Metadata lookup | MusicBrainz (musicbrainzngs) | Artist, label, year, catalogue |
| Metadata lookup 2 | Discogs API | Strong for electronic music |
| Database | SQLite + sqlite-vec extension | Local, no server, vector search built in |
| Embeddings | sentence-transformers | Local, free, CPU-only is fine |
| AI — crate fill | Claude API (claude-sonnet-4-20250514) | Via Anthropic API |
| External similarity | Spotify Web API (spotipy) | Phase 2 |
| Backend | Python + FastAPI | Serves the React frontend |
| Frontend | React + Vite | Library view, crates, set planner |

---

## Key Design Decisions

- **Local first.** SQLite only, no Postgres, no external database service in v1.
- **No manual tagging.** The data layer populates itself. Users never fill in fields.
- **Crate descriptions are plain language.** No filter UI for defining crates — only
  for browsing the library.
- **Corrections are silent.** Every manual add/remove is logged but no UI calls
  attention to it.
- **AI is never load-bearing alone.** Every AI call has a non-AI fallback (the
  SQL+vector result without Claude ranking is still usable).
- **Prompts are versioned files,** not inline strings. Change prompts like code.
- **Derived scores are recomputable.** Store them for query performance but never
  treat them as immutable.
- **Schema follows data, not the other way around.** Do not finalise the database
  schema until the raw outputs of every data source have been researched and mapped.

---

## Settled Decisions

- SQLite + sqlite-vec (not PostgreSQL + pgvector) — keep everything local
- Essentia for all audio analysis (not librosa) — more complete feature set
- FastAPI backend (not Django, not Flask)
- React + Vite frontend
- Claude API for crate fill, next track, description refinement
- AcoustID + MusicBrainz for track identification
- Discogs for label/catalogue enrichment
- uv for Python package management
- Ruff for linting and formatting
- pytest for testing

---

## Open Decisions

These must not be implemented until the relevant research is done:

- **Database schema** — not finalised. Must be designed after mapping the exact
  outputs of all data sources (AcoustID, MusicBrainz, Discogs, Essentia, file tags).
- **Derived score formulas** — not finalised. energy_score, darkness_score,
  groove_score formulas must be validated against real tracks before being locked in.
- **Embeddings storage** — separate table vs sqlite-vec native column
- **File watcher implementation** — watchdog vs polling
- **Frontend component library** — none chosen yet
- **Whether to stream crate fill response** or wait for full result
- **Spotify integration scope** in phase 2
- **sentence-transformers model choice** — all-MiniLM-L6-v2 is a candidate
  but not validated

---

## Data Sources — What Each Provides

> This section is filled in as each source is researched.
> Do not assume fields exist until they are confirmed here.

### File tags (mutagen)
*To be researched. Expected: title, artist, album, year, bpm, format, bitrate,
duration, sample_rate. Reliability on a DJ library TBD.*

### AcoustID + MusicBrainz
*To be researched. Expected: recording ID, title, artist, album, label, year,
catalogue number, genre tags. Match rate and field reliability TBD.*

### Discogs API
*To be researched. Expected: label, catalogue number, release year, genre,
style tags. Coverage for electronic music TBD.*

### Essentia (audio analysis)
Researched. Native outputs:

```
RhythmExtractor2013   →  bpm, bpm_confidence, beat_ticks, bpm_intervals
KeyExtractor (edma)   →  key, key_scale, key_strength
LoudnessEBUR128       →  loudness_lufs (integrated), dynamic_range (LRA)
SpectralCentroidTime  →  spectral_centroid (mean across frames, 0–1)
EnergyBandRatio       →  sub_bass_energy (20–100Hz), high_freq_energy (8kHz+)
PredominantPitchMelodia → vocal_presence (mean confidence, 0–1)
```

Custom computations derived from Essentia outputs:
```
beat_regularity   →  1 - (std / mean) of bpm_intervals
intro_length      →  bars before energy envelope crosses 50% of track mean
outro_length      →  bars after energy drops below 50% of track mean
```

Notes:
- RhythmExtractor2013 requires 44100 Hz. Set minTempo=100, maxTempo=160 for techno/house.
- KeyExtractor: always use profileType='edma' for electronic music.
- LoudnessEBUR128 requires stereo input — use StereoMuxer on mono audio.
- ML models (EffNet genre classifier) require 16000 Hz and separate model files.
- Derived score formulas (energy_score, darkness_score, groove_score) are
  provisional and must be validated against real tracks before use.

---

## Import Pipeline (intended design — not yet built)

Order of operations for a single track. Each step is independent — partial failures
do not block subsequent steps.

```
1. Hash check       — skip if file unchanged (same path + same hash)
2. Read file tags   — mutagen, instant, no network
3. AcoustID         — fingerprint + query, ~2s, needs network
4. MusicBrainz      — fetch full metadata using recording ID from step 3
5. Discogs          — enrich label/catalogue where MusicBrainz is weak
6. Essentia         — local audio analysis, ~5–15s per track, no network
7. Compute scores   — derived scores from Essentia features
8. Write to DB      — single INSERT OR REPLACE
```

Parallelism: steps 3–5 (network) can run concurrently with step 6 (CPU).
Use ThreadPoolExecutor with workers=2 (Essentia is not fully thread-safe).

Fallback chain for key fields — provisional, to be confirmed after source research:
```
bpm:    Essentia → tag_bpm → None
key:    Essentia → None
title:  mb_title → tag_title → filename stem
artist: mb_artist → tag_artist → None
label:  mb_label → discogs_label → None
year:   mb_year → discogs_year → tag_year → None
```

---

## Database Schema (draft — not finalised)

> Do not implement this schema until all data sources have been researched
> and their outputs confirmed. Fields marked TBC may change.

The schema will be designed around confirmed source outputs. Expected sections:

- File metadata (confirmed from filesystem + mutagen)
- Tag data (from mutagen — reliability TBC)
- MusicBrainz data (fields TBC after research)
- Discogs data (fields TBC after research)
- Essentia audio features (confirmed — see Data Sources above)
- Derived scores (formulas TBC after validation on real tracks)
- Crate tables (stable — see below)
- Usage tracking (last_played_date, play_count)

Crate tables are stable and can be implemented now:

```sql
CREATE TABLE crates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE crate_tracks (
    crate_id        TEXT REFERENCES crates(id) ON DELETE CASCADE,
    track_id        INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    added_by        TEXT DEFAULT 'ai',
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (crate_id, track_id)
);

CREATE TABLE crate_corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    crate_id        TEXT REFERENCES crates(id),
    track_id        INTEGER REFERENCES tracks(id),
    action          TEXT,                       -- 'add' or 'remove'
    corrected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Crate Fill Pipeline (intended design — not yet built)

At 20,000 tracks, sending the full library to Claude is not feasible. Use a
three-stage funnel:

```
Stage 1 — SQL hard filter          20,000 → ~400 candidates    <10ms
Stage 2 — Vector similarity search    400 → 80–100 candidates  <100ms
Stage 3 — Claude final ranking     80–100 → 8–15 final tracks  ~2s, ~$0.01
```

Claude system prompt for crate fill (versioned in prompts/):

```
You are a DJ library assistant for a techno and house DJ.
You select tracks from a pre-filtered library to populate a named crate.

Selection rules:
- Be selective. A crate should have 8–14 tracks, not everything that qualifies.
- Prioritise tracks that fit ALL aspects of the description, not just one.
- Prefer tracks not played recently unless the description says otherwise.
- When in doubt, under-select. The DJ will add manually if needed.

Return ONLY valid JSON, no markdown fences, no preamble:
{"selected_ids": [14, 19, 6], "reasoning": "one sentence", "health_note": "any gaps or concerns"}
```

---

## Project File Structure

```
crate-project/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings loaded from .env
│   ├── database.py          # SQLite connection, schema, migrations
│   ├── importer/
│   │   ├── pipeline.py      # Main import orchestration
│   │   ├── tags.py          # mutagen tag reading
│   │   ├── acoustid.py      # fingerprinting + AcoustID query
│   │   ├── musicbrainz.py   # MusicBrainz metadata fetch
│   │   ├── discogs.py       # Discogs API enrichment
│   │   ├── essentia_analysis.py  # Essentia feature extraction
│   │   └── embeddings.py    # sentence-transformers, sqlite-vec writes
│   ├── crates/
│   │   ├── fill.py          # Three-stage fill pipeline
│   │   ├── prompts.py       # System prompts, versioned
│   │   └── learn.py         # Correction logging, description refinement
│   ├── api/
│   │   ├── tracks.py        # GET /tracks with filter params
│   │   ├── crates.py        # CRUD + fill endpoint
│   │   └── search.py        # Natural language search endpoint
│   └── watcher.py           # File system watcher for auto-import
├── backend/tests/
│   ├── conftest.py
│   ├── test_database.py
│   ├── test_api_tracks.py
│   └── test_importer/
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Library.jsx
│   │   │   ├── Crates.jsx
│   │   │   └── SetPlanner.jsx
│   │   ├── components/
│   │   └── App.jsx
│   └── package.json
├── prompts/                 # Versioned prompt files
│   ├── crate_fill_v1.txt
│   └── next_track_v1.txt
├── evals/                   # Test cases for prompts
│   └── crate_fill/
├── scripts/                 # One-off utility scripts
├── docs/                    # Notes, research outputs, decisions
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── CLAUDE.md
└── CURRENT_STATE.md
```

---

## Environment Variables

```
ANTHROPIC_API_KEY=
ACOUSTID_API_KEY=          # free at acoustid.org/api-key
MUSICBRAINZ_APP=           # "CrateApp/0.1 (your@email.com)"
DISCOGS_TOKEN=             # optional, rate limit is generous
SPOTIFY_CLIENT_ID=         # Phase 2
SPOTIFY_CLIENT_SECRET=     # Phase 2
DB_PATH=./crate.db
MUSIC_FOLDER=              # absolute path to the DJ's music folder
LOG_LEVEL=INFO
```

---

## Build Phases

**Phase 0 — Repository setup (current)**
- [ ] Initialise repo with uv, pyproject.toml, Ruff, pre-commit, pytest
- [ ] GitHub Actions CI pipeline
- [ ] React + Vite frontend scaffold with ESLint + Prettier
- [ ] .env.example, .gitignore, README.md

**Phase 1 — Research and data mapping**
- [ ] Research AcoustID API — exact outputs, rate limits, match rate
- [ ] Research MusicBrainz API — exact outputs, field reliability
- [ ] Research Discogs API — exact outputs, coverage for electronic music
- [ ] Research file tags (mutagen) — what fields exist and reliability on DJ files
- [ ] Map all source outputs side by side into a single field inventory
- [ ] Finalise database schema based on confirmed outputs
- [ ] Validate Essentia on 50 real tracks — calibrate derived score formulas

**Phase 2 — Import pipeline**
- [ ] mutagen tag reading
- [ ] AcoustID fingerprinting + lookup
- [ ] MusicBrainz metadata fetch
- [ ] Discogs enrichment
- [ ] Essentia audio analysis
- [ ] Derived score computation (formulas confirmed in Phase 1)
- [ ] SQLite write with INSERT OR REPLACE

**Phase 3 — Backend API**
- [ ] FastAPI setup
- [ ] /tracks endpoint with filter, sort, group params
- [ ] Basic crate CRUD

**Phase 4 — Frontend library view**
- [ ] Library table with all audio features
- [ ] Filtering, sorting, grouping

**Phase 5 — Intelligence**
- [ ] Vector embeddings on import
- [ ] AI crate fill pipeline (3-stage funnel)
- [ ] Correction logging
- [ ] Description refinement
- [ ] Spotify API integration
- [ ] Natural language search

**Phase 6 — Performance features**
- [ ] Set planner with energy arc
- [ ] Transition compatibility warnings
- [ ] AI next track suggestion
- [ ] Set history logging
- [ ] Export to Pioneer CDJ USB

---

## CURRENT_STATE.md

> Replace this section content with the live CURRENT_STATE.md at the start
> of each session. Do not leave this placeholder in place.

```
Status: not started
Current phase: Phase 0 — repository setup
Next action: initialise crate-project repo using plan-repo-setup.md
Blockers: none
Last session: n/a
Open questions: none
```
