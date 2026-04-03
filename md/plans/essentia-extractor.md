# Implementation Plan: Essentia Audio Analysis Module

## Overview

`backend/importer/essentia_analysis.py` takes a file path and returns a flat dictionary
of raw audio features extracted by Essentia. It runs every standard algorithm and (when
available) the TensorFlow ML models, storing each raw output directly — no derived scores,
no combinations, no aggregation beyond what is needed to reduce a frame-level vector to a
track-level descriptor (mean/variance). The module does not compute `beat_regularity`,
`intro_length`, `energy_score`, or any other derived metric; those belong to a later pipeline
stage. On any failure it returns a dict rather than raising, so the pipeline can always
write a partial result.

---

## Function Interface

```python
def analyse_track(
    file_path: str,
    config: EssentiaConfig,
) -> dict:
    ...
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `file_path` | `str` | Absolute path to the audio file |
| `config` | `EssentiaConfig` | Dataclass of all tuneable settings (see Configuration) |

### Return contract

| Situation | Return value |
|---|---|
| Full success | Dict with all keys populated |
| Partial failure (file loads; one algorithm crashes) | Dict with that algorithm's keys set to `None`; all other keys populated; no `analysis_error` field |
| Total failure (file cannot be loaded) | Dict with every audio key set to `None` plus `analysis_error: str` |
| Unexpected top-level exception | Same as total failure — the outer try/except ensures the function never raises |

Errors are **returned as structured data**, never raised. The caller in `pipeline.py` should
never need to wrap this function in its own try/except.

---

## Audio Loading

The file is read from disk **three times** — once per required sample rate. All loads use
`essentia.standard.MonoLoader`.

| Buffer name | Sample rate | Channels | Loader call | Used by |
|---|---|---|---|---|
| `audio_44k` | 44100 Hz | mono | `MonoLoader(filename, sampleRate=44100)()` | All standard algorithms |
| `audio_stereo` | 44100 Hz | stereo (derived) | `es.StereoMuxer()(audio_44k, audio_44k)` | LoudnessEBUR128 only |
| `audio_16k` | 16000 Hz | mono | `MonoLoader(filename, sampleRate=16000)()` | All ML models |

`audio_stereo` is derived from `audio_44k` via `StereoMuxer` — it duplicates the mono
channel, so it is not an additional disk read.

If `config.run_ml_models` is `False`, `audio_16k` is never loaded.

**Load order:** Load `audio_44k` first. If it fails, set `analysis_error` and return
immediately without attempting `audio_16k` or running any algorithm.

---

## Standard Algorithm Pipeline

Frame-level algorithms (MFCC, BarkBands, SpectralCentroidTime, EnergyBandRatio,
TuningFrequency) share a single framing pass — see Frame-Level Processing below.

| Algorithm | Config | Input buffer | Essentia output fields captured | Dict key(s) |
|---|---|---|---|---|
| `RhythmExtractor2013` | `method='multifeature'`, `minTempo=config.min_tempo`, `maxTempo=config.max_tempo` | `audio_44k` | `bpm`, `ticks`, `confidence`, `estimates`, `bpmIntervals` | `bpm`, `beat_ticks`, `bpm_confidence`, `bpm_estimates`, `bpm_intervals` |
| `Danceability` | defaults | `audio_44k` | `danceability`, `dfa` | `danceability`, `danceability_dfa` |
| `KeyExtractor` | `profileType='edma'` | `audio_44k` | `key`, `scale`, `strength` | `key`, `key_scale`, `key_strength` |
| `TuningFrequency` | defaults | spectral peaks from frame loop (see below) | `tuningFrequency`, `tuningCents` | `tuning_frequency_hz`, `tuning_cents` |
| `LoudnessEBUR128` | defaults | `audio_stereo` | `momentaryLoudness`, `shortTermLoudness`, `integratedLoudness`, `loudnessRange` | `momentary_loudness`, `short_term_loudness`, `integrated_loudness`, `loudness_range` |
| `DynamicComplexity` | defaults | `audio_44k` | `dynamicComplexity`, `loudness` | `dynamic_complexity`, `dynamic_complexity_loudness` |
| `SpectralCentroidTime` | defaults | per-frame (frame loop) | `centroid` (Hz) | `spectral_centroid_hz` (mean across frames) |
| `EnergyBandRatio` (sub-bass) | `startFrequency=20`, `stopFrequency=100` | spectrum per frame | `energyBandRatio` | `sub_bass_ratio` (mean across frames) |
| `EnergyBandRatio` (high-freq) | `startFrequency=8000`, `stopFrequency=22050` | spectrum per frame | `energyBandRatio` | `high_freq_ratio` (mean across frames) |
| `MFCC` | `numberCoefficients=13`, `numberBands=40` | spectrum per frame | `mfcc` (13-element vector) | `mfcc_mean` (mean vector), `mfcc_var` (variance vector) |
| `BarkBands` | `numberBands=27` | spectrum per frame | `bands` (27-element vector) | `bark_bands_mean` (mean vector across frames) |
| `PredominantPitchMelodia` | defaults | `audio_44k` | `pitch`, `pitchConfidence` | `pitch_frames`, `pitch_confidence_frames` (JSON blobs, not aggregated) |
| `OnsetRate` | none | `audio_44k` | `onsets`, `onsetRate` | `onset_times`, `onset_rate` |

**Note on TuningFrequency:** This algorithm takes spectral peak frequencies and magnitudes,
not raw audio. It must be fed the accumulated peaks from the frame loop (see Frame-Level
Processing). Instantiate `SpectralPeaks` inside the frame loop alongside `Spectrum`.

---

## Frame-Level Processing

A single framing pass feeds MFCC, BarkBands, SpectralCentroidTime, EnergyBandRatio
(both instances), SpectralPeaks (for TuningFrequency), and Windowing.

### Setup

```
frameSize  = 2048
hopSize    = 1024
windowType = 'hann'
```

### Algorithm chain per frame

```
FrameGenerator(audio_44k, frameSize=2048, hopSize=1024)
  → Windowing(type='hann')
  → Spectrum()                          # magnitude spectrum, size = frameSize/2 + 1 = 1025
  → MFCC(numberCoefficients=13, numberBands=40)
  → BarkBands(numberBands=27)
  → SpectralCentroidTime()              # operates on raw frame (not spectrum)
  → EnergyBandRatio(sub-bass instance)  # takes spectrum
  → EnergyBandRatio(high-freq instance) # takes spectrum
  → SpectralPeaks()                     # frequencies + magnitudes for TuningFrequency
```

`SpectralCentroidTime` takes the windowed frame (time-domain), not the spectrum.
All other spectral algorithms take the magnitude spectrum output of `Spectrum`.

### Aggregation

| Algorithm | Aggregation |
|---|---|
| MFCC | `np.mean(frames, axis=0)` → `mfcc_mean`; `np.var(frames, axis=0)` → `mfcc_var` |
| BarkBands | `np.mean(frames, axis=0)` → `bark_bands_mean` |
| SpectralCentroidTime | `float(np.mean(centroids))` → `spectral_centroid_hz` |
| EnergyBandRatio (sub-bass) | `float(np.mean(ratios))` → `sub_bass_ratio` |
| EnergyBandRatio (high-freq) | `float(np.mean(ratios))` → `high_freq_ratio` |
| SpectralPeaks | Concatenate all frame peaks → pass full set to `TuningFrequency` once after loop |

---

## ML Model Pipeline

All ML models require `essentia-tensorflow`. An import guard at **module load time**
sets a flag:

```python
try:
    import essentia.tensorflow  # noqa: F401
    _TF_AVAILABLE = True
except ImportError:
    _TF_AVAILABLE = False
```

If `_TF_AVAILABLE` is `False` or `config.run_ml_models` is `False`, all ML fields are
set to `None` without logging a warning — this is expected in CI and lightweight imports.

If a model file path does not exist, log a `WARNING` and set that model's fields to `None`.
Do not abort other ML models.

All four model families run inside a single `_run_ml_models(audio_16k, config)` helper
function. This keeps ML-specific imports and error handling isolated from the standard
pipeline.

### Discogs-EffNet — Classification (400 classes)

| Item | Detail |
|---|---|
| Algorithm | `essentia.standard.TensorflowPredictEffnetDiscogs` |
| Model file param | `graphFilename=config.model_dir / 'discogs-effnet-bs64-1.pb'` |
| Metadata file | `config.model_dir / 'discogs-effnet-bs64-1.json'` (label list) |
| Input | `audio_16k` (16000 Hz mono) |
| Raw output | `predictions` — vector of 400 probabilities |
| Dict keys | `genre_probabilities` (full 400-float list, JSON), `genre_top_labels` (top-N label strings, JSON) |
| Top-N | `config.genre_top_n` (default 5); extract by argsort descending on probabilities vector, read label strings from metadata JSON |
| Fallback | `None` for both keys if TF unavailable or model file missing |

### Discogs-EffNet — Embeddings

The embeddings are extracted from the **same forward pass** as classification using the
`TensorflowPredictEffnetDiscogs` algorithm with output layer set to the penultimate layer.
This is **one model file**, not two separate files.

| Item | Detail |
|---|---|
| Algorithm | `TensorflowPredictEffnetDiscogs` with `output='DiscogsEffnet/dense/BiasAdd'` (confirm layer name from model metadata JSON) |
| Model file | Same `.pb` file as classification |
| Raw output | Embedding vector (dimension confirmed from model metadata JSON at runtime) |
| Dict key | `embedding` (full float list, JSON) — this goes into sqlite-vec |
| Fallback | `None` if TF unavailable or model file missing |

**Open question Q-effnet-layer:** The exact output layer name for embeddings must be
confirmed from the model metadata JSON when the file is downloaded. The plan defers
this to Phase 2 implementation. Interim decision: parse the metadata JSON at runtime
to discover the layer name rather than hardcoding it.

### Mood — Arousal/Valence (DEAM regression)

| Item | Detail |
|---|---|
| Algorithm | `essentia.standard.TensorflowPredict2D` (regression model) |
| Model file param | `graphFilename=config.model_dir / 'deam-msd-musicnn-2.pb'` |
| Input | Embeddings from a MusiCNN model at 16000 Hz (or use EffNet embeddings if model supports it — confirm from model metadata) |
| Raw output | 2-element vector: `[arousal, valence]` on DEAM scale [1, 9] |
| Dict keys | `arousal` (float), `valence` (float) |
| Fallback | `None` for both if TF unavailable or model file missing |

**Note:** The mood models consume intermediate embeddings, not raw audio directly. The
pipeline must run EffNet or MusiCNN first to get embeddings, then pass them to the mood
model. Confirm the exact embedding source from model metadata during Phase 2.

### Voice/Instrumental Classifier

| Item | Detail |
|---|---|
| Algorithm | `essentia.standard.TensorflowPredict2D` (binary classifier) |
| Model file param | `graphFilename=config.model_dir / 'voice_instrumental-discogs-effnet-1.pb'` |
| Input | EffNet embeddings from the classification pass |
| Raw output | 2-element vector `[instrumental_prob, voice_prob]` |
| Dict key | `voice_probability` — store `output[1]` (voice probability, float [0, 1]) |
| Fallback | `None` if TF unavailable or model file missing |

**Efficiency note:** The voice classifier consumes EffNet embeddings that are already
computed during the classification pass. Run classification first and reuse the embedding
output — do not load or run EffNet a second time.

---

## Output Schema

Lists are stored as JSON blobs in SQLite. `← JSON` indicates the column type is TEXT.

| Key | Source algorithm | Essentia field | Python type | Range / Units | Nullable? |
|---|---|---|---|---|---|
| `bpm` | RhythmExtractor2013 | `bpm` | `float` | BPM, [0, ∞) | None on failure |
| `bpm_confidence` | RhythmExtractor2013 | `confidence` | `float` | [0, 5.32] | None on failure |
| `beat_ticks` | RhythmExtractor2013 | `ticks` | `list[float]` | seconds ← JSON | None on failure |
| `bpm_estimates` | RhythmExtractor2013 | `estimates` | `list[float]` | BPM ← JSON | None on failure |
| `bpm_intervals` | RhythmExtractor2013 | `bpmIntervals` | `list[float]` | seconds ← JSON | None on failure |
| `danceability` | Danceability | `danceability` | `float` | [0, ~3] | None on failure |
| `danceability_dfa` | Danceability | `dfa` | `list[float]` | — ← JSON | None on failure |
| `key` | KeyExtractor | `key` | `str` | A, Bb, B, C, C#, D, Eb, E, F, F#, G, Ab | None on failure |
| `key_scale` | KeyExtractor | `scale` | `str` | major / minor | None on failure |
| `key_strength` | KeyExtractor | `strength` | `float` | [0, 1] | None on failure |
| `tuning_frequency_hz` | TuningFrequency | `tuningFrequency` | `float` | Hz | None on failure |
| `tuning_cents` | TuningFrequency | `tuningCents` | `float` | ~[-35, 65] cents | None on failure |
| `integrated_loudness` | LoudnessEBUR128 | `integratedLoudness` | `float` | LUFS (typically -20 to -6) | None on failure |
| `loudness_range` | LoudnessEBUR128 | `loudnessRange` | `float` | LU (typically 3–14) | None on failure |
| `momentary_loudness` | LoudnessEBUR128 | `momentaryLoudness` | `list[float]` | LUFS ← JSON | None on failure |
| `short_term_loudness` | LoudnessEBUR128 | `shortTermLoudness` | `list[float]` | LUFS ← JSON | None on failure |
| `dynamic_complexity` | DynamicComplexity | `dynamicComplexity` | `float` | dB | None on failure |
| `dynamic_complexity_loudness` | DynamicComplexity | `loudness` | `float` | dB | None on failure |
| `spectral_centroid_hz` | SpectralCentroidTime | `centroid` (mean) | `float` | Hz (expected ~500–5000) | None on failure |
| `sub_bass_ratio` | EnergyBandRatio (20–100 Hz) | `energyBandRatio` (mean) | `float` | [0, 1] | None on failure |
| `high_freq_ratio` | EnergyBandRatio (8–22050 Hz) | `energyBandRatio` (mean) | `float` | [0, 1] | None on failure |
| `mfcc_mean` | MFCC | `mfcc` (mean across frames) | `list[float]` | 13 floats ← JSON | None on failure |
| `mfcc_var` | MFCC | `mfcc` (var across frames) | `list[float]` | 13 floats ← JSON | None on failure |
| `bark_bands_mean` | BarkBands | `bands` (mean across frames) | `list[float]` | 27 floats ← JSON | None on failure |
| `pitch_frames` | PredominantPitchMelodia | `pitch` | `list[float]` | Hz (0 = unvoiced) ← JSON | None on failure |
| `pitch_confidence_frames` | PredominantPitchMelodia | `pitchConfidence` | `list[float]` | [0, 1] ← JSON | None on failure |
| `onset_times` | OnsetRate | `onsets` | `list[float]` | seconds ← JSON | None on failure |
| `onset_rate` | OnsetRate | `onsetRate` | `float` | onsets/s | None on failure |
| `genre_probabilities` | TensorflowPredictEffnetDiscogs | `predictions` | `list[float]` | 400 floats [0,1] ← JSON | None if TF unavailable |
| `genre_top_labels` | TensorflowPredictEffnetDiscogs | top-N from `predictions` | `list[str]` | N label strings ← JSON | None if TF unavailable |
| `embedding` | TensorflowPredictEffnetDiscogs | penultimate layer output | `list[float]` | floats ← JSON | None if TF unavailable |
| `arousal` | TensorflowPredict2D (DEAM) | output[0] | `float` | [1, 9] | None if TF unavailable |
| `valence` | TensorflowPredict2D (DEAM) | output[1] | `float` | [1, 9] | None if TF unavailable |
| `voice_probability` | TensorflowPredict2D (voice) | output[1] | `float` | [0, 1] | None if TF unavailable |
| `essentia_version` | `essentia.__version__` | — | `str` | — | always set |
| `analysis_timestamp` | `datetime.utcnow().isoformat()` | — | `str` | ISO 8601 | always set |
| `analysis_error` | internal | — | `str` | error message | only set on total failure |

---

## Error Handling

| Failure mode | Strategy |
|---|---|
| `MonoLoader` raises on corrupt file or unsupported format | Catch in outer try/except around load; set all audio keys to `None`; set `analysis_error = str(exception)`; return immediately |
| Any standard algorithm raises | Catch per-algorithm in individual try/except; log `WARNING` with algorithm name and exception; set that algorithm's output keys to `None`; continue |
| Frame loop raises on a single frame | Catch inside the frame loop; skip that frame; if too many frames fail, set all frame-derived keys to `None` after the loop |
| `essentia-tensorflow` not installed | `ImportError` caught at module load; `_TF_AVAILABLE = False`; all ML keys silently set to `None` — not an error |
| ML model file missing | Check `Path(path).exists()` before instantiating; log `WARNING`; set that model's keys to `None`; continue with other ML models |
| `_run_ml_models` raises unexpectedly | Catch at the call site; log `WARNING`; set all ML keys to `None`; continue to metadata fields |
| Top-level unexpected exception | Outermost try/except around the entire function body; set all keys to `None`; set `analysis_error`; always return a dict |

The function must never raise. `analysis_error` is only present in the returned dict when
the file could not be loaded at all. Per-algorithm failures do not set `analysis_error`.

---

## Thread Safety

- **All algorithm instances are created inside `analyse_track`**, not at module level.
  No algorithm object is shared across calls or threads.
- The module-level `_TF_AVAILABLE` flag is read-only after import — safe to read from
  multiple threads.
- **TensorFlow session state:** TensorFlow (as used by essentia-tensorflow) is not
  guaranteed thread-safe when multiple sessions are active concurrently. With
  `max_workers=2`, two ML inference calls may overlap. Mitigation: wrap
  `_run_ml_models` in a per-process threading lock if TF session errors are observed
  during Phase 2 testing. Do not pre-emptively add a lock — measure first.
- **Confirmed max worker count: 2** (from CLAUDE.md). Do not increase without
  testing thread safety with per-thread instances on the actual hardware.

---

## Configuration

All tuneable values live in an `EssentiaConfig` dataclass in `backend/config.py`.
The function takes `config: EssentiaConfig` as its second argument; nothing is hardcoded
in the analysis module itself.

| Parameter | Controls | Location | Default |
|---|---|---|---|
| `min_tempo` | `RhythmExtractor2013` `minTempo` | `EssentiaConfig` | `100` |
| `max_tempo` | `RhythmExtractor2013` `maxTempo` | `EssentiaConfig` | `160` |
| `genre_top_n` | How many top genre labels to store in `genre_top_labels` | `EssentiaConfig` | `5` |
| `model_dir` | Directory where TF `.pb` and `.json` model files are stored | `EssentiaConfig` | `Path('./models')` |
| `run_ml_models` | Skip entire ML section (for fast imports or missing TF) | `EssentiaConfig` | `True` |
| `run_pitch_analysis` | Skip `PredominantPitchMelodia` (slow, ~10–30 s per track) | `EssentiaConfig` | `True` |

When `run_pitch_analysis` is `False`, `pitch_frames` and `pitch_confidence_frames` are
set to `None` without logging a warning.

---

## Test Plan

Tests live in `backend/tests/test_importer/test_essentia_analysis.py`.

### Synthetic audio fixture

Generate a 4-second 440 Hz sine wave at 44100 Hz using numpy, save to a temp WAV file
via `scipy.io.wavfile.write` or `soundfile.write`. No real music files in the test suite.

```python
@pytest.fixture
def sine_wav(tmp_path):
    sr = 44100
    t = np.linspace(0, 4, sr * 4, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t)
    path = tmp_path / "sine.wav"
    soundfile.write(str(path), audio, sr)
    return str(path)
```

Use a config with `run_ml_models=False` and `run_pitch_analysis=False` for all standard
tests so CI runs in seconds.

### Core assertions

- Return value is a `dict`.
- All expected keys are present (compare against a hardcoded key list).
- Numeric keys that are not `None` are within documented ranges:
  - `bpm_confidence` in `[0, 5.32]`
  - `key_strength` in `[0, 1]`
  - `sub_bass_ratio` in `[0, 1]`
  - `high_freq_ratio` in `[0, 1]`
  - `danceability` >= 0
- List fields (`beat_ticks`, `mfcc_mean`, etc.) deserialise correctly from JSON (i.e., are
  already Python lists in the returned dict; the caller is responsible for serialising to
  JSON before writing to SQLite).
- `essentia_version` and `analysis_timestamp` are always non-None strings.

### Failure path tests

- Pass a nonexistent file path → `analysis_error` is set, all audio keys are `None`,
  `essentia_version` and `analysis_timestamp` are still set.
- Pass a path to a zero-byte file → same expectation.

### ML import guard test

Use `unittest.mock.patch` to make `essentia.tensorflow` unimportable at module reload
time (or set `_TF_AVAILABLE = False` directly if the module exposes it). Confirm
`genre_probabilities`, `embedding`, `arousal`, `valence`, `voice_probability` are all
`None` without any exception.

### Speed strategy

- `run_ml_models=False` and `run_pitch_analysis=False` in all CI fixtures.
- Full pipeline test (all algorithms enabled) lives in a separate test marked
  `@pytest.mark.slow` and excluded from the default `pytest` run.
- CI runs `pytest -m "not slow"`.

---

## Open Questions

The research doc lists 10 open questions. Those relevant to this module:

| # | Question | Blocks plan? | Interim decision |
|---|---|---|---|
| Q9 | `essentia-tensorflow` wheel availability for Python 3.11 | **No** — deferred | Plan assumes Python 3.10 as the safe choice for essentia-tensorflow until confirmed otherwise. The `_TF_AVAILABLE` flag means the module degrades gracefully if TF is absent. Confirm at start of Phase 2 before setting the project Python version. |
| Q8 | WSL I/O latency when music files are on `/mnt/c/` or `/mnt/d/` | **No** — deferred | Document the latency risk in Phase 2 setup notes. If `/mnt/` latency is severe, recommend symlinking the music folder into the WSL filesystem. Do not change the module design. |
| Q7 | Thread safety at workers > 2 with per-thread algorithm instances | **No** — deferred | Plan locks max workers at 2 as stated in CLAUDE.md. If tests show TF session conflicts even at 2 workers, add a threading lock around `_run_ml_models`. Revisit if 2 workers proves to be a bottleneck. |
| Q3 | PredominantPitchMelodia behaviour on instrumental tracks | **No** — deferred | The plan stores `pitch_frames` and `pitch_confidence_frames` as raw vectors without interpreting them. Whether the algorithm tracks synths rather than vocals does not affect what we store. The interpretation (vocal vs synth) is a later-stage concern. |
| Q1 | SpectralCentroidTime practical Hz range on real techno | **No** — deferred | Store Hz value as-is. Do not normalise. The range will be calibrated during Phase 2 validation on 50 real tracks. |
| Q2 | RhythmExtractor2013 confidence thresholds on electronic music | **No** — deferred | Store raw confidence value [0, 5.32]. Threshold for "needs review" flag is a Phase 2 calibration decision. |

Questions Q4 (edma vs bgate), Q5 (Danceability scale), Q6 (LoudnessEBUR128 on short
tracks), Q10 (intro/outro formula) do not affect this module — they affect derived score
computation or schema design, which is deferred to Phase 2.

---

## Implementation Order

1. **Create `EssentiaConfig` dataclass** in `backend/config.py` with all parameters from
   the Configuration section. Add default values. No logic — just the dataclass.

2. **Scaffold `essentia_analysis.py`** with the function signature, the `_TF_AVAILABLE`
   import guard, and the top-level try/except returning an empty error dict. Confirm the
   module imports without errors in WSL.

3. **Implement audio loading** — `audio_44k` load + `audio_stereo` via StereoMuxer.
   Add the total-failure path (MonoLoader raises → return error dict).

4. **Implement the frame loop** — FrameGenerator, Windowing, Spectrum, then MFCC,
   BarkBands, SpectralCentroidTime, both EnergyBandRatio instances, SpectralPeaks.
   Accumulate results into lists. After the loop, aggregate to mean/variance vectors.

5. **Implement TuningFrequency** — pass accumulated spectral peaks from the frame loop.

6. **Implement remaining standard algorithms** one at a time, each in its own try/except:
   RhythmExtractor2013, Danceability, KeyExtractor, LoudnessEBUR128, DynamicComplexity,
   OnsetRate.

7. **Implement PredominantPitchMelodia** behind the `run_pitch_analysis` flag.

8. **Implement `_run_ml_models`** — EffNet classification + embeddings, then mood
   arousal/valence, then voice classifier. Each model in its own try/except. Gate on
   `_TF_AVAILABLE` and `config.run_ml_models`.

9. **Assemble the return dict** — all keys, metadata fields, no `analysis_error` on
   success.

10. **Write the test file** — synthetic fixture, core key assertions, failure path tests,
    ML import guard test. Confirm all tests pass in WSL.

11. **Mark slow tests** with `@pytest.mark.slow` and verify `pytest -m "not slow"` passes
    in CI.

12. **Run the full pipeline manually** on 3–5 real tracks in WSL to confirm outputs look
    sane before Phase 2 integration work begins.
