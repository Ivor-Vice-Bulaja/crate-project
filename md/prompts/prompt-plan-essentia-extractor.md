# Task: Plan the Essentia Audio Analysis Module

## Context

Read CLAUDE.md before starting. This is a planning task — no code is written here.
The output is a detailed implementation plan that will be used to build
`backend/importer/essentia_analysis.py` in Phase 2.

The research for this plan is complete. All Essentia algorithm details, exact field
names, value ranges, and constraints are documented in `docs/research/essentia.md`.
Read that document in full before producing any plan — do not rely on prior knowledge
about Essentia.

**Core principle:** This module extracts raw Essentia outputs and returns them as a flat
dictionary. It does not compute derived features, scores, or combinations. Store everything
Essentia gives us; let later stages decide what to do with it. The goal is to lose
as little information as possible from each algorithm's outputs.

---

## What to plan

Design the implementation of `backend/importer/essentia_analysis.py` — the module
that takes a file path and returns a flat dictionary of raw audio features ready to
be written to the SQLite database.

### 1. Module interface

Define the exact function signature and return type. The function will be called from
`backend/importer/pipeline.py` in a ThreadPoolExecutor.

- What does the function take as input? (file path, any config?)
- What does it return on success? (flat dict of raw outputs)
- What does it return on partial failure (file loads but one algorithm crashes)?
- What does it return on total failure (file cannot be loaded at all)?
- Should errors be raised or returned as structured data?

### 2. Audio loading strategy

Multiple algorithms require different sample rates:
- Most algorithms: 44100 Hz mono
- ML models (EffNet genre, mood, voice): 16000 Hz mono
- TempoCNN: 11025 Hz mono
- LoudnessEBUR128: 44100 Hz **stereo** (StereoMuxer duplicates the mono channel)

Decide:
- How many times is the file read from disk?
- When is each audio buffer prepared?
- How is the stereo buffer created for LoudnessEBUR128?

### 3. Standard algorithm pipeline

Specify every standard algorithm to run (no ML). For each:

| Algorithm | Config | Input buffer | Essentia output fields to capture | Dict key(s) |
|---|---|---|---|---|

Algorithms to include:

**Rhythm/Tempo**
- RhythmExtractor2013: `method='multifeature', minTempo=100, maxTempo=160`
  Capture all 5 outputs: `bpm`, `ticks`, `confidence`, `estimates`, `bpmIntervals`
- Danceability (default config)
  Capture: `danceability` (scalar), `dfa` (vector)

**Key/Tonality**
- KeyExtractor: `profileType='edma'`
  Capture all 3 outputs: `key`, `scale`, `strength`
- TuningFrequency (requires spectral peaks — specify how to compute them)
  Capture: `tuningFrequency`, `tuningCents`

**Loudness/Dynamics**
- LoudnessEBUR128 (stereo input)
  Capture all 4 outputs: `momentaryLoudness` (vector), `shortTermLoudness` (vector),
  `integratedLoudness` (scalar), `loudnessRange` (scalar)
- DynamicComplexity
  Capture: `dynamicComplexity`, `loudness`

**Spectral/Timbral**
- SpectralCentroidTime (note: output is in Hz, not [0, 1])
  Capture: `centroid` (Hz) — store as `spectral_centroid_hz`
- Two EnergyBandRatio instances:
  - sub-bass: `startFrequency=20, stopFrequency=100`
  - high-freq: `startFrequency=8000, stopFrequency=22050`
  Each has one output `energyBandRatio` — store as `sub_bass_ratio` and `high_freq_ratio`
- MFCC (mean and variance across frames — specify frame/hop size and aggregation)
  Capture: mean vector and variance vector of the 13 coefficients
- BarkBands (mean across frames)
  Capture: mean of the 27-band energy vector

**Vocal/Melodic**
- PredominantPitchMelodia (default config)
  Capture both raw vectors: `pitch` (Hz per frame), `pitchConfidence` (per frame)
  Store as JSON blobs — do not aggregate yet

**Onset**
- OnsetRate
  Capture: `onsets` (positions), `onsetRate` (rate per second)

For frame-level algorithms (MFCC, BarkBands, SpectralCentroidTime): specify the
framing setup (FrameGenerator + Windowing + Spectrum) that feeds them, including
frameSize and hopSize values.

### 4. ML model pipeline

The ML models are part of this module. They require `essentia-tensorflow` (not plain
`essentia`) and separately downloaded model files. All models use 16000 Hz mono audio.

For each model, specify:
- Which `essentia-tensorflow` algorithm wraps it
- Configuration (model file path param, batch size, etc.)
- What the raw outputs are (probabilities vector, embedding vector)
- How the output maps to dict key(s)
- Fallback when `essentia-tensorflow` is not installed or model file is missing

**Discogs-EffNet — classification (400 classes)**
- Raw output: vector of 400 probabilities, one per Discogs style
- Store: full vector as a JSON blob (all 400 values); also store top-N label strings
  (N is configurable) so genre data is human-readable without unpacking the blob
- Also serves as the embedding backbone — same forward pass produces embeddings

**Discogs-EffNet — embeddings**
- Raw output: embedding vector (dimension TBD from model metadata)
- Store: full vector — this goes into sqlite-vec for similarity search
- Decide: is this a separate model file or extracted from the classification model?

**Mood / Arousal-Valence**
- Arousal and valence regression (DEAM dataset scale)
- Raw output: two scalar values
- Store as `arousal` (float) and `valence` (float)

**Voice/Instrumental classifier**
- Raw output: probability of voice presence
- Store as `voice_probability` (float, [0, 1])

For all ML models, address:
- Import guard: if `import essentia.tensorflow` fails, skip all ML and return None
  for ML fields — do not crash
- Missing model file: log a warning and return None for that model's fields
- Should all ML models run in a single function or be separated?

### 5. Output schema

Define the complete return dictionary. For every key:
- Key name (snake_case)
- Source algorithm and exact Essentia output field name
- Python type
- Value range or units
- Nullable? (and when)

The plan must include at minimum these fields:

```
# Rhythm
bpm                    float   BPM             None on failure
bpm_confidence         float   [0, 5.32]       None on failure
beat_ticks             list    seconds         None on failure   ← JSON
bpm_estimates          list    BPM             None on failure   ← JSON
bpm_intervals          list    seconds         None on failure   ← JSON
danceability           float   [0, ~3]         None on failure
danceability_dfa       list    —               None on failure   ← JSON

# Key
key                    str     A–G             None on failure
key_scale              str     major/minor     None on failure
key_strength           float   [0, 1]          None on failure
tuning_frequency_hz    float   Hz              None on failure
tuning_cents           float   cents           None on failure

# Loudness
integrated_loudness    float   LUFS            None on failure
loudness_range         float   LU              None on failure
dynamic_complexity     float   dB              None on failure
momentary_loudness     list    LUFS            None on failure   ← JSON
short_term_loudness    list    LUFS            None on failure   ← JSON

# Spectral
spectral_centroid_hz   float   Hz              None on failure
sub_bass_ratio         float   [0, 1]          None on failure
high_freq_ratio        float   [0, 1]          None on failure
mfcc_mean              list    13 floats       None on failure   ← JSON
mfcc_var               list    13 floats       None on failure   ← JSON
bark_bands_mean        list    27 floats       None on failure   ← JSON

# Vocal/melodic
pitch_frames           list    Hz              None on failure   ← JSON
pitch_confidence_frames list   [0, 1]          None on failure   ← JSON

# Onsets
onset_times            list    seconds         None on failure   ← JSON
onset_rate             float   onsets/s        None on failure

# ML models (require essentia-tensorflow)
genre_probabilities    list    400 floats      None if unavailable  ← JSON, Discogs-EffNet
genre_top_labels       list    str             None if unavailable  ← top-N label strings
embedding              list    floats          None if unavailable  ← sqlite-vec
arousal                float   [1, 9]          None if unavailable
valence                float   [1, 9]          None if unavailable
voice_probability      float   [0, 1]          None if unavailable

# Metadata
essentia_version       str     —               always set
analysis_timestamp     str     ISO 8601        always set
```

### 6. Error handling

- MonoLoader failure (corrupt file, unsupported format): return dict with all audio
  fields as None plus an `analysis_error` string field. Do not raise.
- Per-algorithm failure: catch, log the exception and algorithm name, set that
  algorithm's output keys to None, continue with remaining algorithms.
- ML import failure: catch ImportError at module load time; set a flag that skips
  ML section silently.
- Missing model file: check path before loading; log warning; set model's fields to None.
- Top-level fallback: the entire function should be wrapped to never raise — it should
  always return a dict (possibly with many None values and an error field).

### 7. Thread safety

- All algorithm instances must be created inside the function, not at module level.
- TensorFlow session state: specify whether TF models require any special handling
  for concurrent calls (e.g. per-thread sessions).
- State the confirmed max worker count: 2 (from CLAUDE.md).

### 8. Configuration

Identify every value that should not be hardcoded. For each:
- What it controls
- Where it lives (function argument, config dataclass, `backend/config.py`)
- Its default value

At minimum:
- `min_tempo` / `max_tempo` for RhythmExtractor2013
- `genre_top_n` — how many top genre labels to store
- `model_dir` — directory where TF model files are stored
- `run_ml_models` — boolean flag to skip ML entirely (for fast imports or missing TF)
- `run_pitch_analysis` — boolean flag for PredominantPitchMelodia (slow, ~10–30 s)

### 9. Test plan

Describe the tests for `backend/tests/test_importer/test_essentia_analysis.py`:

- **Synthetic audio fixture:** generate a short (3–5 s) numpy sine wave at 44100 Hz
  as a WAV file in a tmp directory. No real music files in the test suite.
- **Core assertions:** the return dict contains all expected keys; numeric values
  are within documented ranges; list fields deserialise correctly from JSON.
- **Speed:** synthetic audio runs fast enough for CI. PredominantPitchMelodia and
  ML models should be gated behind config flags that are off in tests.
- **Failure path:** test that a nonexistent file path returns a dict with
  `analysis_error` set and all audio fields as None.
- **ML models:** test the import-guard path (mock `essentia.tensorflow` as unavailable)
  to confirm ML fields come back as None without crashing.

### 10. Open questions from the research doc

`docs/research/essentia.md` has 10 open questions. For each one that affects
this module, state whether it blocks the implementation plan or can be deferred,
and what the interim decision is.

Key questions to address:
- `essentia-tensorflow` wheel availability for Python 3.11 — does this block the plan?
- WSL I/O latency when music files are on the Windows filesystem at `/mnt/c/` or `/mnt/d/`
- Thread safety at workers > 2 with per-thread algorithm instances

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/essentia-extractor.md
```

Structure:

```
# Implementation Plan: Essentia Audio Analysis Module

## Overview
One paragraph: what the module does, what it does not do.

## Function Interface
Exact signature, return type, error contract.

## Audio Loading
How many disk reads, which loaders, how each sample-rate buffer is prepared.

## Standard Algorithm Pipeline
Table: algorithm | config | input buffer | Essentia outputs captured | dict keys

## Frame-Level Processing
The FrameGenerator + Windowing + Spectrum setup feeding MFCC, BarkBands, etc.

## ML Model Pipeline
For each model: TF algorithm, audio prep, raw output, dict key, unavailability fallback.

## Output Schema
Full table: key | source field | type | range/units | nullable

## Error Handling
Specific strategy for each failure mode.

## Thread Safety
Instance strategy, TF session notes, worker limit.

## Configuration
Table: parameter | controls | location | default

## Test Plan
Fixtures, core assertions, speed strategy, failure path tests.

## Open Questions
Each relevant research question, plus interim decision.

## Implementation Order
Numbered steps to build this module in Phase 2.
```

---

## Definition of done

- [ ] `md/plans/essentia-extractor.md` exists
- [ ] Standard algorithm pipeline table covers every algorithm listed in section 3
- [ ] ML model pipeline covers all four model families in section 4
- [ ] Output schema table covers every field listed in section 5
- [ ] No derived features anywhere in the plan — only raw Essentia outputs
- [ ] Error handling is specific for each failure mode
- [ ] Test plan specifies synthetic audio fixture and CI speed strategy
- [ ] All open questions that affect the plan have a stated interim decision
- [ ] Implementation order is a concrete numbered list
