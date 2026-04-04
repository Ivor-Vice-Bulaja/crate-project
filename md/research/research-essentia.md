# Essentia Research

Researched: 2026-04-02
Researcher: Claude Code (claude-sonnet-4-6)
Phase: Phase 1 — data source research

---

## Sources

- https://essentia.upf.edu/documentation.html — overview, architecture, modes
- https://essentia.upf.edu/reference/ — full algorithm index
- https://essentia.upf.edu/models.html — ML models catalogue
- https://essentia.upf.edu/installing.html — installation instructions
- https://essentia.upf.edu/streaming_extractor_music.html — MusicExtractor output fields
- https://github.com/MTG/essentia — GitHub README
- Individual algorithm pages: std_RhythmExtractor2013, std_BeatTrackerMultiFeature,
  std_BeatTrackerDegara, std_Danceability, std_PercivalBpmEstimator, std_KeyExtractor,
  std_Key, std_HPCP, std_LoudnessEBUR128, std_Loudness, std_DynamicComplexity,
  std_MFCC, std_SpectralCentroidTime, std_EnergyBandRatio, std_EnergyBand,
  std_BarkBands, std_SpectralContrast, std_PredominantPitchMelodia, std_PitchYin,
  std_OnsetDetection, std_Onsets, std_OnsetRate, std_MonoLoader, std_AudioLoader,
  std_EasyLoader, std_SBic, std_TempoCNN, std_TonalExtractor, std_TuningFrequency,
  std_RhythmDescriptors, std_ChordsDetection, std_BeatsLoudness, std_ReplayGain,
  std_LoopBpmEstimator, std_LowLevelSpectralExtractor

---

## What Essentia Is

Essentia is an open-source C++ library with Python and JavaScript bindings for audio
analysis and music information retrieval, developed by the Music Technology Group (MTG)
at Universitat Pompeu Fabra, Barcelona. It is released under the Affero GPLv3 license
(commercial licenses available on request).

**Design philosophy:** Essentia is a collection of algorithms, not a framework. The user
controls the analysis flow; the library handles algorithm implementation. This makes it
highly composable — you chain together exactly the algorithms you need.

### Processing Modes

**Standard mode:** Algorithms are called explicitly in user-defined order. Each algorithm
is instantiated, configured, fed inputs, and its outputs read manually. More verbose but
easier to debug.

```python
import essentia.standard as es

loader = es.MonoLoader(filename='track.mp3', sampleRate=44100)
audio = loader()

rhythm = es.RhythmExtractor2013(method='multifeature')
bpm, ticks, confidence, estimates, bpmIntervals = rhythm(audio)
```

**Streaming mode:** Algorithms connect via named ports and form a dataflow graph, similar
to Max/MSP or PureData. Less boilerplate code and lower memory consumption (processes
data as it flows). Better for long files.

```python
import essentia.streaming as es
# algorithms are connected with >> and the network is run once
```

### Packages

| Package | Contains | Install |
|---|---|---|
| `essentia` | All standard algorithms, no TensorFlow | `pip install essentia` |
| `essentia-tensorflow` | All of `essentia` + TensorFlow-based ML models | `pip install essentia-tensorflow` |

The two packages conflict — install one or the other, not both.

### Platform Support

| Platform | Status |
|---|---|
| Linux x86_64, i686 | Fully supported; pip wheels available |
| macOS | Supported; build from source or use conda |
| Windows | C++ library compiles via MinGW cross-compilation; **Python bindings not supported natively** — use WSL |
| iOS / Android | Supported (C++ only, no Python) |
| JavaScript (Web) | Via Emscripten cross-compilation |

**Windows note for Crate:** Python bindings do not work on native Windows. The development
machine must use WSL (Windows Subsystem for Linux) or a Linux Docker container. The
production deployment (if any) should target Linux. See Installation section below.

---

## Algorithm Reference

### Rhythm and Tempo

#### RhythmExtractor2013

The primary beat-tracking and tempo estimation algorithm. Wraps either BeatTrackerMultiFeature
or BeatTrackerDegara.

**Python name:** `essentia.standard.RhythmExtractor2013`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `signal` | vector_real | mono audio signal |

**Outputs:**
| Name | Type | Range/Units | Description |
|---|---|---|---|
| `bpm` | real | [0, ∞) bpm | estimated tempo |
| `ticks` | vector_real | seconds | beat positions |
| `confidence` | real | [0, 5.32] | confidence of tick detection (0 when method='degara') |
| `estimates` | vector_real | bpm | BPM distribution characterisation (multiple candidates) |
| `bpmIntervals` | vector_real | seconds | measured intervals between consecutive beats |

> **CLAUDE.md discrepancy:** CLAUDE.md names this output `beat_ticks`. The actual output
> field name is `ticks`, not `beat_ticks`. The field `bpmIntervals` is correct (matching
> `bpm_intervals` after Python snake_case normalisation). The field `bpm_confidence` in
> CLAUDE.md maps to the actual output named `confidence`.

**Config params:**
| Param | Type | Default | Range | Notes |
|---|---|---|---|---|
| `minTempo` | integer | 40 | [40, 180] | slowest detectable BPM |
| `maxTempo` | integer | 208 | [60, 250] | fastest detectable BPM |
| `method` | string | `multifeature` | {multifeature, degara} | underlying algorithm |

**Input requirements:**
- Sample rate **must be 44100 Hz** — the algorithm will produce incorrect results otherwise
- Mono signal

**For techno/house:** Set `minTempo=100, maxTempo=160` to avoid octave errors (detecting
at 65 bpm instead of 130 bpm). The `multifeature` method is more accurate; `degara` is
faster but produces no confidence score.

**Computing beat_regularity from outputs:**
```python
import numpy as np
bpm_intervals = bpmIntervals  # output from RhythmExtractor2013
if len(bpm_intervals) > 1:
    beat_regularity = 1.0 - (np.std(bpm_intervals) / np.mean(bpm_intervals))
else:
    beat_regularity = None  # not enough beats
```

---

#### BeatTrackerMultiFeature

More accurate beat tracker using five onset detection functions combined. Used internally
by RhythmExtractor2013 when `method='multifeature'`.

**Python name:** `essentia.standard.BeatTrackerMultiFeature`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `signal` | vector_real | mono audio signal at 44100 Hz |

**Outputs:**
| Name | Type | Range/Units | Description |
|---|---|---|---|
| `ticks` | vector_real | seconds | estimated beat positions |
| `confidence` | real | [0, 5.32] | beat tracker confidence |

**Confidence thresholds:**
- [0, 1): very low confidence — result likely wrong
- [1, 1.5]: low confidence
- (1.5, 3.5]: good confidence (~80% beat accuracy)
- (3.5, 5.32]: excellent confidence

**Config params:**
| Param | Type | Default | Range |
|---|---|---|---|
| `minTempo` | integer | 40 | [40, 180] bpm |
| `maxTempo` | integer | 208 | [60, 250] bpm |

**Input requirements:** 44100 Hz mono, same as RhythmExtractor2013.

---

#### BeatTrackerDegara

Faster but less accurate beat tracker based on complex spectral difference. Used internally
by RhythmExtractor2013 when `method='degara'`. No confidence output.

**Python name:** `essentia.standard.BeatTrackerDegara`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `signal` | vector_real | mono audio signal at 44100 Hz |

**Outputs:**
| Name | Type | Range/Units | Description |
|---|---|---|---|
| `ticks` | vector_real | seconds | estimated beat positions |

**Config params:** `minTempo` (int, default 40), `maxTempo` (int, default 208) — same ranges as above.

**Input requirements:** 44100 Hz. Uses 2048/1024 frame/hop with 2× posterior resampling.

---

#### Danceability

Estimates danceability using Detrended Fluctuation Analysis (DFA) of the signal envelope.
Higher values indicate more regular, dance-suitable rhythmic structure.

**Python name:** `essentia.standard.Danceability`

**Inputs:**
| Name | Type |
|---|---|
| `signal` | vector_real |

**Outputs:**
| Name | Type | Range | Description |
|---|---|---|---|
| `danceability` | real | [0, ~3] | danceability score; higher = more danceable |
| `dfa` | vector_real | — | DFA exponent vector for each segment length tau |

**Config params:**
| Param | Type | Default | Range | Description |
|---|---|---|---|---|
| `minTau` | real | 310 | (0, ∞) ms | minimum segment length |
| `maxTau` | real | 8800 | (0, ∞) ms | maximum segment length |
| `sampleRate` | real | 44100 | (0, ∞) Hz | |
| `tauMultiplier` | real | 1.1 | (1, ∞) | increment multiplier from minTau to maxTau |

**Note:** The scale [0, ~3] is unusual. Do not normalise to [0, 1] without understanding the
distribution on your actual tracks first. This algorithm is unrelated to the ML-based
Danceability classifiers in the models section.

---

#### PercivalBpmEstimator

Autocorrelation-based tempo estimator. Good for loops and short clips. Returns only a
single BPM value with no confidence score.

**Python name:** `essentia.standard.PercivalBpmEstimator`

**Inputs:**
| Name | Type |
|---|---|
| `signal` | vector_real |

**Outputs:**
| Name | Type | Units | Description |
|---|---|---|---|
| `bpm` | real | bpm | tempo estimation |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `frameSize` | integer | 1024 | frame size for signal analysis |
| `frameSizeOSS` | integer | 2048 | frame size for Onset Strength Signal analysis |
| `hopSize` | integer | 128 | hop size for signal analysis |
| `hopSizeOSS` | integer | 128 | hop size for OSS analysis |
| `maxBPM` | integer | 210 | maximum BPM to detect |
| `minBPM` | integer | 50 | minimum BPM to detect |
| `sampleRate` | integer | 44100 | Hz |

---

#### LoopBpmEstimator

BPM estimator for loops. Returns 0 if confidence is below threshold.

**Python name:** `essentia.standard.LoopBpmEstimator`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `bpm` | real | estimated BPM, or 0.0 if unreliable |

**Config params:** `confidenceThreshold` (real, default 0.95, range [0, 1])

---

#### TempoCNN (ML-based)

Deep learning BPM estimator. Requires `essentia-tensorflow` and a downloaded model file.
More accurate on complex, variable-tempo material.

**Python name:** `essentia.standard.TempoCNN`

**Inputs:** `audio` (vector_real) — **must be 11025 Hz** (not 44100 Hz)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `globalTempo` | real | overall BPM |
| `localTempo` | vector_real | per-patch BPM estimates |
| `localTempoProbabilities` | vector_real | per-patch tempo probabilities |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `graphFilename` | string | "" | path to downloaded TF model file |
| `savedModel` | string | "" | path to TF SavedModel (alternative to graphFilename) |
| `aggregationMethod` | string | majority | {majority, mean, median} |
| `batchSize` | integer | 64 | -1 or 0 = single session |
| `patchHopSize` | integer | 128 | frames between patches |
| `lastPatchMode` | string | discard | {discard, repeat} |

**Pipeline:** `MonoLoader(sampleRate=11025) >> TempoCNN(...)`

**Model download:** See https://essentia.upf.edu/models.html — TempoCNN section.

---

#### RhythmDescriptors

High-level rhythm extractor combining RhythmExtractor2013 with BpmHistogramDescriptors.
Convenient wrapper that returns all rhythm features in one call.

**Python name:** `essentia.standard.RhythmDescriptors`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `beats_position` | vector_real | beat positions in seconds |
| `confidence` | real | beat tracking confidence |
| `bpm` | real | tempo in BPM |
| `bpm_estimates` | vector_real | multiple BPM candidates |
| `bpm_intervals` | vector_real | inter-beat intervals |
| `first_peak_bpm` | real | primary BPM histogram peak |
| `first_peak_spread` | real | primary peak spread |
| `first_peak_weight` | real | primary peak weight |
| `second_peak_bpm` | real | secondary BPM histogram peak |
| `second_peak_spread` | real | secondary peak spread |
| `second_peak_weight` | real | secondary peak weight |
| `histogram` | vector_real | full BPM histogram |

No config params documented.

---

#### BeatsLoudness

Per-beat energy analysis useful for characterising kick drum presence and groove.

**Python name:** `essentia.standard.BeatsLoudness`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `loudness` | vector_real | energy of each beat across the whole spectrum |
| `loudnessBandRatio` | vector_vector_real | energy ratio per beat per frequency band |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `beats` | vector_real | [] | beat positions in seconds (required input — pass ticks from RhythmExtractor2013) |
| `beatDuration` | real | 0.05 s | window after beat where energy is measured |
| `beatWindowDuration` | real | 0.1 s | window around beat to search for peak |
| `frequencyBands` | vector_real | [20, 150, 400, 3200, 7000, 22000] Hz | band boundaries |
| `sampleRate` | real | 44100 | Hz |

**Note:** Returns empty if `beats` param is empty. Must be passed beat positions first.

---

### Key and Tonality

#### KeyExtractor

The recommended high-level key detector. Takes raw audio and returns key, scale, and
confidence in one call. Wraps HPCP computation and Key internally.

**Python name:** `essentia.standard.KeyExtractor`

**Inputs:**
| Name | Type |
|---|---|
| `audio` | vector_real |

**Outputs:**
| Name | Type | Range | Description |
|---|---|---|---|
| `key` | string | A, Bb, B, C, C#, D, Eb, E, F, F#, G, Ab | detected key |
| `scale` | string | {major, minor} | detected scale |
| `strength` | real | [0, 1] | key detection confidence |

> **CLAUDE.md claim:** `key_scale` — the actual output field is named `scale`, not `key_scale`.
> The KeyExtractor outputs `key`, `scale`, and `strength`. When accessed via the MusicExtractor
> pool, the fields become `key_temperley`, `key_krumhansl`, `key_edma` (one per profile type).

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `profileType` | string | bgate | see profile type table below |
| `frameSize` | integer | 4096 | |
| `hopSize` | integer | 4096 | |
| `hpcpSize` | integer | 12 | HPCP output size (multiple of 12) |
| `sampleRate` | real | 44100 | Hz |
| `minFrequency` | real | 25 | Hz |
| `maxFrequency` | real | 3500 | Hz |
| `maximumSpectralPeaks` | integer | 60 | |
| `pcpThreshold` | real | 0.2 | [0, 1] |
| `spectralPeaksThreshold` | real | 0.0001 | |
| `tuningFrequency` | real | 440 | Hz |
| `weightType` | string | cosine | {cosine, squaredCosine, none} |
| `windowType` | string | hann | |
| `averageDetuningCorrection` | bool | true | shift PCP to nearest tempered bin |

**profileType options:** diatonic, krumhansl, temperley, weichai, tonictriad, temperley2005,
thpcp, shaath, gomez, noland, faraldo, pentatonic, edmm, edma, bgate, braw

**For electronic music:** Use `profileType='edma'` (Electronic Dance Music Analysis). This
profile is specifically designed for music without strong tonal centres, which is common
in techno. The CLAUDE.md recommendation is confirmed correct.

---

#### Key

Lower-level algorithm that takes a precomputed PCP (pitch class profile) and returns key.
Used by KeyExtractor internally. Useful if you already have HPCP computed.

**Python name:** `essentia.standard.Key`

**Inputs:** `pcp` (vector_real) — pitch class profile

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `key` | string | A through G |
| `scale` | string | major or minor |
| `strength` | real | confidence [0, 1] |
| `firstToSecondRelativeStrength` | real | strength difference between top two candidates |

**Config params:**
| Param | Type | Default |
|---|---|---|
| `profileType` | string | bgate |
| `pcpSize` | integer | 36 |
| `numHarmonics` | integer | 4 |
| `slope` | real | 0.6 |
| `useMajMin` | bool | false |
| `usePolyphony` | bool | true |
| `useThreeChords` | bool | true |

---

#### HPCP (Harmonic Pitch Class Profile)

Computes the harmonic pitch class profile — a 12-bin (or higher resolution) representation
of which pitch classes are active in a spectrum. The foundation for key detection and
chord analysis.

**Python name:** `essentia.standard.HPCP`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `frequencies` | vector_real | spectral peak frequencies in Hz |
| `magnitudes` | vector_real | spectral peak magnitudes |

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `hpcp` | vector_real | harmonic pitch class profile (size = `size` param) |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `size` | integer | 12 | output bins; must be multiple of 12 |
| `referenceFrequency` | real | 440 | Hz (A3 reference) |
| `harmonics` | integer | 0 | 0 = fundamental only; n = include n harmonics |
| `bandPreset` | bool | true | use band preset |
| `bandSplitFrequency` | real | 500 | Hz |
| `minFrequency` | real | 40 | Hz |
| `maxFrequency` | real | 5000 | Hz |
| `maxShifted` | bool | false | shift so max peak is at index 0 |
| `nonLinear` | bool | false | post-processing for contrast near 0/1 |
| `normalized` | string | unitMax | {none, unitSum, unitMax} |
| `weightType` | string | squaredCosine | {none, cosine, squaredCosine} |
| `windowSize` | real | 1 | semitones [0, 12] |
| `sampleRate` | real | 44100 | Hz |

**Constraints:** At least 200 Hz gap required between minFrequency, bandSplitFrequency, and maxFrequency.

---

#### TonalExtractor

High-level wrapper computing all tonal features from raw audio in one call.

**Python name:** `essentia.standard.TonalExtractor`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `key_key` | string | detected key |
| `key_scale` | string | major or minor |
| `key_strength` | real | key detection confidence |
| `chords_key` | string | most common chord root |
| `chords_scale` | string | major or minor |
| `chords_progression` | vector_string | chord labels over time |
| `chords_strength` | vector_real | per-chord confidence |
| `chords_changes_rate` | real | chord changes per second |
| `chords_number_rate` | real | ratio of distinct chords |
| `chords_histogram` | vector_real | chord distribution |
| `hpcp` | vector_vector_real | HPCP frames |
| `hpcp_highres` | vector_vector_real | high-resolution HPCP frames |

**Config params:** `frameSize` (int, default 4096), `hopSize` (int, default 2048),
`tuningFrequency` (real, default 440 Hz)

---

#### ChordsDetection

Detects chord progressions from a sequence of HPCP frames.

**Python name:** `essentia.standard.ChordsDetection`

**Inputs:** `pcp` (vector_vector_real) — sequence of HPCP frames

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `chords` | vector_string | chord labels (A, Bb, B, C, C#, D, Eb, E, F, F#, G, Ab — major/minor implied) |
| `strength` | vector_real | per-chord confidence |

**Config params:** `hopSize` (int, default 2048), `sampleRate` (real, default 44100),
`windowSize` (real, default 2 s)

**Note:** Experimental status. Only detects major and minor triads.

---

#### TuningFrequency

Estimates the tuning reference frequency of a track (whether it is tuned to A=440 Hz or
detuned). Useful for detecting tracks that will clash harmonically when mixed.

**Python name:** `essentia.standard.TuningFrequency`

**Inputs:** `frequencies` (vector_real), `magnitudes` (vector_real) — spectral peaks

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `tuningFrequency` | real | estimated tuning frequency in Hz |
| `tuningCents` | real | deviation from A=440 Hz, range approximately [-35, 65] cents |

---

### Loudness and Dynamics

#### LoudnessEBUR128

Implements the EBU R128 broadcast loudness standard. The most accurate and musically
relevant loudness measurement for DJ use. Requires **stereo input**.

**Python name:** `essentia.standard.LoudnessEBUR128`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `signal` | vector_stereosample | **stereo** audio signal (not mono) |

**Outputs:**
| Name | Type | Range/Units | Description |
|---|---|---|---|
| `momentaryLoudness` | vector_real | LUFS | loudness in 400 ms windows |
| `shortTermLoudness` | vector_real | LUFS | loudness in 3 s windows |
| `integratedLoudness` | real | LUFS (typically -20 to -6) | overall track loudness with gating |
| `loudnessRange` | real | LU (dB) | dynamic range (LRA); typically 3–14 LU for electronic music |

> **CLAUDE.md discrepancy:** CLAUDE.md uses the field name `loudness_lufs` for the integrated
> loudness output. The actual field name is `integratedLoudness`. The field `dynamic_range`
> in CLAUDE.md maps to `loudnessRange`. When stored in a database, rename these to
> `integrated_loudness_lufs` and `loudness_range_lu` for clarity.

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `hopSize` | real | 0.1 | (0, 0.1] seconds |
| `sampleRate` | real | 44100 | Hz |
| `startAtZero` | bool | false | window timing reference |

**Processing detail:** Applies K-weighting (shelving + high-pass filter), then computes
loudness via sliding windows. Uses -70 LUFS absolute silence gate for integrated loudness;
-70 LUFS and -20 LU relative gates for loudness range.

**Stereo requirement:** Must use `StereoMuxer` on mono audio before passing to this algorithm.
```python
audio_stereo = es.StereoMuxer()(audio_mono, audio_mono)
loudness_algo = es.LoudnessEBUR128()
momentary, short_term, integrated, loudness_range = loudness_algo(audio_stereo)
```

---

#### Loudness

Simple psychoacoustic loudness based on Stevens' power law. Faster than EBU R128 but less
accurate for broadcast-standard measurements.

**Python name:** `essentia.standard.Loudness`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `loudness` | real | signal energy raised to power 0.67 (arbitrary units, not LUFS) |

No config params.

---

#### DynamicComplexity

Measures loudness variation over time — higher values indicate more dynamic, less compressed
audio. Useful for detecting over-limited/brickwalled masters.

**Python name:** `essentia.standard.DynamicComplexity`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `dynamicComplexity` | real | average absolute deviation from global loudness level [dB] |
| `loudness` | real | estimated overall loudness [dB] |

**Config params:** `frameSize` (real, default 0.2 s), `sampleRate` (real, default 44100 Hz)

---

#### ReplayGain

Computes the ReplayGain correction value needed to normalise the track to a target level.

**Python name:** `essentia.standard.ReplayGain`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `replayGain` | real | distance to ~-31 dBB SMPTE reference level [dB] |

**Config params:** `sampleRate` (real, default 44100 Hz)

---

### Spectral and Timbral

#### MFCC (Mel-Frequency Cepstral Coefficients)

Timbral descriptor set widely used as a feature fingerprint. Not directly human-interpretable
but useful as input to similarity search and ML models.

**Python name:** `essentia.standard.MFCC`

**Inputs:** `spectrum` (vector_real) — magnitude spectrum (from Spectrum algorithm)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `bands` | vector_real | energy in each mel band (size = `numberBands`) |
| `mfcc` | vector_real | MFCC coefficients (size = `numberCoefficients`) |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `numberBands` | integer | 40 | mel filterbank bands |
| `numberCoefficients` | integer | 13 | DCT output coefficients |
| `lowFrequencyBound` | real | 0 | Hz |
| `highFrequencyBound` | real | 11000 | Hz |
| `sampleRate` | real | 44100 | Hz |
| `logType` | string | dbamp | {natural, dbpow, dbamp, log} |
| `dctType` | integer | 2 | [2, 3] |
| `normalize` | string | unit_sum | {unit_sum, unit_tri, unit_max} |
| `warpingFormula` | string | htkMel | {slaneyMel, htkMel} |
| `weighting` | string | warping | {warping, linear} |
| `inputSize` | integer | 1025 | expected spectrum size |
| `type` | string | power | {magnitude, power} |
| `liftering` | integer | 0 | liftering coefficient |
| `silenceThreshold` | real | 1e-10 | |

**Typical usage:** Compute frame-by-frame then aggregate (mean, variance) for a track-level
descriptor. Default produces 13 coefficients from a 40-band mel filterbank (MFCC-FB40).

---

#### SpectralCentroidTime

The "brightness" of a sound — higher centroid means more high-frequency content.

**Python name:** `essentia.standard.SpectralCentroidTime`

**Inputs:** `array` (vector_real) — the input signal or frame

**Outputs:**
| Name | Type | Range/Units | Description |
|---|---|---|---|
| `centroid` | real | Hz | spectral centroid of the signal |

> **CLAUDE.md discrepancy:** CLAUDE.md claims the output range is [0, 1] and calls the field
> `spectral_centroid`. The actual output is in **Hz** (not normalised 0–1). The output field
> name is `centroid`. For techno tracks, typical values are roughly 1000–4000 Hz depending on
> how many high-frequency elements are present. If you want a [0, 1] normalised value, divide
> by Nyquist (sampleRate / 2). This is a significant discrepancy — the database schema should
> store the Hz value, not an assumed [0, 1] value.

**Config params:** `sampleRate` (real, default 44100 Hz)

**Note on usage with CLAUDE.md:** The CLAUDE.md assumption that this algorithm produces a
[0, 1] normalised value is **incorrect**. The output is in Hz. Additionally, the algorithm
computes centroid from a first-difference filtered version of the input (time-domain method),
not from a spectrum. For spectrum-domain centroid, use the `Centroid` algorithm on the output
of `Spectrum`.

---

#### EnergyBandRatio

Computes the fraction of total spectral energy within a specific frequency band.

**Python name:** `essentia.standard.EnergyBandRatio`

**Inputs:** `spectrum` (vector_real) — magnitude spectrum

**Outputs:**
| Name | Type | Range | Description |
|---|---|---|---|
| `energyBandRatio` | real | [0, 1] | energy ratio of specified band to total spectrum |

> **CLAUDE.md discrepancy:** CLAUDE.md refers to outputs `sub_bass_energy (20–100Hz)` and
> `high_freq_energy (8kHz+)` as if they are named fields. In reality, `EnergyBandRatio` takes
> no frequency band in its output — it has a single output `energyBandRatio` which is the ratio
> for whichever band you configured. You must instantiate **two separate** `EnergyBandRatio`
> instances to get sub-bass and high-frequency ratios:

```python
sub_bass = es.EnergyBandRatio(startFrequency=20, stopFrequency=100, sampleRate=44100)
high_freq = es.EnergyBandRatio(startFrequency=8000, stopFrequency=22050, sampleRate=44100)

sub_bass_ratio = sub_bass(spectrum)   # energyBandRatio output
high_freq_ratio = high_freq(spectrum) # energyBandRatio output
```

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `startFrequency` | real | 0 | Hz |
| `stopFrequency` | real | 100 | Hz |
| `sampleRate` | real | 44100 | Hz |

**Related:** `EnergyBand` computes the absolute energy (not ratio) in a band.

---

#### EnergyBand

Absolute energy (not ratio) in a specified frequency band.

**Python name:** `essentia.standard.EnergyBand`

**Inputs:** `spectrum` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `energyBand` | real | energy in the specified frequency band |

**Config params:** `startCutoffFrequency` (real, default 0 Hz), `stopCutoffFrequency`
(real, default 100 Hz), `sampleRate` (real, default 44100 Hz)

---

#### BarkBands

Spectral energy in perceptual Bark scale bands. 27 bands covering 0–27 kHz. The first two
standard Bark bands are subdivided for improved beat detection resolution.

**Python name:** `essentia.standard.BarkBands`

**Inputs:** `spectrum` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `bands` | vector_real | energy per Bark band (size = `numberBands`) |

**Config params:**
| Param | Type | Default | Range |
|---|---|---|---|
| `numberBands` | integer | 27 | [1, 28] |
| `sampleRate` | real | 44100 | [0, ∞) Hz |

---

#### SpectralContrast

Captures timbral texture by measuring the difference between spectral peaks and valleys
across sub-bands. Useful for distinguishing audio character (e.g., full mix vs. sparse elements).

**Python name:** `essentia.standard.SpectralContrast`

**Inputs:** `spectrum` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `spectralContrast` | vector_real | contrast coefficients (size = `numberBands`) |
| `spectralValley` | vector_real | valley magnitudes (size = `numberBands`) |

**Config params:**
| Param | Type | Default |
|---|---|---|
| `frameSize` | integer | 2048 |
| `numberBands` | integer | 6 |
| `lowFrequencyBound` | real | 20 Hz |
| `highFrequencyBound` | real | 11000 Hz |
| `neighbourRatio` | real | 0.4 |
| `staticDistribution` | real | 0.15 |
| `sampleRate` | real | 22050 Hz |

**Note:** Default `sampleRate` is 22050, unlike most other algorithms which default to 44100.

---

### Vocal and Melodic

#### PredominantPitchMelodia

Extracts the main melodic line as pitch contours with confidence scores. For techno/house,
primarily useful for detecting presence of vocals or lead synth lines.

**Python name:** `essentia.standard.PredominantPitchMelodia`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Range | Description |
|---|---|---|---|
| `pitch` | vector_real | Hz or 0 | estimated pitch per frame (0 = unvoiced) |
| `pitchConfidence` | vector_real | [0, 1] | confidence per frame |

> **CLAUDE.md discrepancy:** CLAUDE.md claims the output is `vocal_presence (mean confidence, 0–1)`
> as a single scalar. The actual outputs are `pitch` (vector of Hz values) and `pitchConfidence`
> (vector of per-frame confidences). There is **no single `vocal_presence` output field**. To
> derive a scalar vocal presence estimate, you would compute the mean of `pitchConfidence` frames
> where `pitch > 0`:

```python
pitch, pitch_confidence = predominant_pitch(audio)
voiced_frames = pitch > 0
vocal_presence = float(np.mean(pitch_confidence[voiced_frames])) if voiced_frames.any() else 0.0
```

This derived metric is reasonable but not a built-in Essentia output.

**Config params (key ones):**
| Param | Type | Default | Description |
|---|---|---|---|
| `sampleRate` | real | 44100 | Hz |
| `frameSize` | integer | 2048 | |
| `hopSize` | integer | 128 | |
| `minFrequency` | real | 80 | Hz |
| `maxFrequency` | real | 20000 | Hz |
| `voicingTolerance` | real | 0.2 | [-1.0, 1.4] |
| `guessUnvoiced` | bool | false | estimate pitch in unvoiced segments |

---

#### PitchYin

Frame-level fundamental frequency estimation (monophonic). Lower-level than PredominantPitchMelodia.

**Python name:** `essentia.standard.PitchYin`

**Inputs:** `signal` (vector_real) — one audio frame

**Outputs:**
| Name | Type | Range | Description |
|---|---|---|---|
| `pitch` | real | Hz | detected pitch (undefined when confidence = 0) |
| `pitchConfidence` | real | [0, 1] | detection confidence |

**Config params:**
| Param | Type | Default |
|---|---|---|
| `frameSize` | integer | 2048 |
| `sampleRate` | real | 44100 |
| `minFrequency` | real | 20 Hz |
| `maxFrequency` | real | 22050 Hz |
| `interpolate` | bool | true |
| `tolerance` | real | 0.15 |

---

### Structure and Segmentation

#### OnsetDetection

Per-frame onset detection function value. A single real number per frame indicating
transient likelihood. Must be accumulated into a vector then passed to Onsets.

**Python name:** `essentia.standard.OnsetDetection`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `spectrum` | vector_real | magnitude spectrum |
| `phase` | vector_real | phase vector (only used by 'complex' method) |

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `onsetDetection` | real | detection function value for the current frame |

**Config params:**
| Param | Type | Default | Options |
|---|---|---|---|
| `method` | string | hfc | {hfc, complex, complex_phase, flux, melflux, rms} |
| `sampleRate` | real | 44100 | Hz |

**Methods:**
- `hfc` — High Frequency Content, best for percussive events (kicks, snares)
- `complex` — Complex spectral difference, considers magnitude and phase
- `flux` — Spectral flux, general-purpose
- `melflux` — Spectral difference in mel bands
- `rms` — RMS-based onset detection

---

#### Onsets

Converts accumulated onset detection function frames into onset time positions.

**Python name:** `essentia.standard.Onsets`

**Inputs:**
| Name | Type | Description |
|---|---|---|
| `detections` | matrix_real | rows = detection functions, columns = frames |
| `weights` | vector_real | weight per detection function |

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `onsets` | vector_real | onset positions in seconds |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `alpha` | real | 0.1 | [0, 1] |
| `delay` | integer | 5 | frames |
| `frameRate` | real | 86.1328 | frames/s (optimised for 44100/512) |
| `silenceThreshold` | real | 0.02 | [0, 1] |

---

#### OnsetRate

High-level onset detector returning positions and rate in one call.

**Python name:** `essentia.standard.OnsetRate`

**Inputs:** `signal` (vector_real)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `onsets` | vector_real | onset positions in seconds |
| `onsetRate` | real | onsets per second |

No config params. Requires 44100 Hz input.

---

#### SBic (Segmentation via Bayesian Information Criterion)

Identifies homogeneous audio segments where feature vectors share a similar distribution.
Useful for detecting structural boundaries (intro, breakdown, outro, drop).

**Python name:** `essentia.standard.SBic`

**Inputs:** `features` (matrix_real) — feature matrix (rows = features, columns = frames)

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `segmentation` | vector_real | frame indices where segments begin/end |

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `cpw` | real | 1.5 | complexity penalty weight |
| `inc1` | integer | 60 | first pass increment (frames) |
| `inc2` | integer | 20 | second pass increment (frames) |
| `minLength` | integer | 10 | minimum segment length (frames) |
| `size1` | integer | 300 | first pass window size (frames) |
| `size2` | integer | 200 | second pass window size (frames) |

**Note for intro/outro detection:** SBic detects all segment boundaries. Deriving
`intro_length` and `outro_length` requires additional logic (find first segment end,
last segment start). Consider using the energy envelope approach instead of SBic for
DJ-specific intro/outro detection — it is simpler and more reliable on electronic music.

---

## ML Models Reference

All models require `essentia-tensorflow` (not plain `essentia`). All require model files
downloaded separately from https://essentia.upf.edu/models.html. License: CC BY-NC-SA 4.0
for MTG models (non-commercial). Commercial licensing available from MTG.

All models default to CPU inference. GPU support exists via TensorFlow but is not required.

### Discogs-EffNet (Audio Embeddings + Genre Classification)

**Task:** Multi-label genre/style classification; audio embeddings for similarity search.

**Input requirements:**
- Sample rate: 16000 Hz
- Channels: mono
- Batch size: 64 (fixed in TF version; dynamic in ONNX version)

**Model variants:**
| Variant | Output | Description |
|---|---|---|
| Classification (400) | 400 probabilities | Discogs 400-style genre classification |
| Classification (519) | 519 probabilities | Discogs 519-style genre classification |
| Embeddings | Feature vector | General audio embeddings for similarity |
| Artist embeddings | Feature vector | Artist-level similarity |
| Label embeddings | Feature vector | Label-level similarity |
| Track embeddings | Feature vector | Track-level similarity |
| Multi-task | Multiple | Combined prediction |

**Formats:** TensorFlow `.pb` + `.json` metadata; ONNX (dynamic batch) also available.

**DJ relevance:** High. The 400/519 style tags include detailed electronic music taxonomy
(Techno, House, Deep House, Minimal Techno, Tech House, etc.). This is the most directly
useful ML model for Crate's genre classification.

**Pipeline:** `MonoLoader(sampleRate=16000) >> TensorflowPredictEffnetDiscogs`

---

### MAEST (Music Audio Efficient Spectrogram Transformer)

**Task:** Style classification and rich audio embeddings using transformer architecture.

**Input requirements:**
- Sample rate: 16000 Hz
- Segment lengths: 5 s, 10 s, 20 s, or 30 s (model variant determines this)
- Output shape: `(batch_size, 1, tokens, embedding_size)`

**Variants:** Multiple sequence lengths × different initializations (DeiT, PaSST, random)
× teacher-student versions.

**Formats:** TensorFlow (fixed batch size 1), ONNX (dynamic).

**DJ relevance:** High. Produces 519 Discogs-style embeddings/probabilities. More accurate
than EffNet for complex classification but slower.

---

### TempoCNN

**Task:** Deep learning BPM estimation.

**Input requirements:**
- Sample rate: 11025 Hz (non-standard — requires resampling)
- Algorithm: `TempoCNN` (see Rhythm section above)

**DJ relevance:** High. More accurate than RhythmExtractor2013 on complex or variable-tempo
material. Recommended as a fallback or cross-check for tracks where RhythmExtractor2013
gives low confidence.

---

### Mood and Affect Models

**Task:** Classify mood/affect from audio.

**Input requirements:** 16000 Hz mono; embeddings from EffNet or MAEST as intermediate step.

**Available classifiers:**
| Model | Task | Output |
|---|---|---|
| Mood Aggressive | binary | aggressive / not aggressive |
| Mood Happy | binary | happy / not happy |
| Mood Party | binary | party / not party |
| Mood Relaxed | binary | relaxed / not relaxed |
| Mood Sad | binary | sad / not sad |
| Moods MIREX | 5-class | cluster labels |
| Arousal/Valence | regression | 2D emotional space (DEAM, emoMusic, MuSe datasets) |
| Danceability | binary | danceable / not danceable |
| Approachability | 2/3-class or regression | mainstream vs niche |
| Engagement | 2/3-class or continuous | active vs background listening |

**DJ relevance:** Medium. The Arousal/Valence regression model is the most useful for
energy matching. The Danceability classifier complements the algorithmic `Danceability`
algorithm.

---

### Instrumentation Models

**Task:** Classify instruments and acoustic properties.

**Available classifiers:**
| Model | Task |
|---|---|
| MTG-Jamendo Instrument | 40 instrument classes |
| Acoustic/Electronic | binary (acoustic vs electronic) |
| Voice/Instrumental | binary |
| Voice Gender | classification |
| Tonal/Atonal | binary |
| Timbre | classification |
| NSynth properties | acoustic/electronic, bright/dark, reverb |

**DJ relevance:** Low–Medium. The Acoustic/Electronic and Voice/Instrumental classifiers
are useful for filtering — a techno DJ rarely wants acoustic tracks.

---

### Genre Classification (MTG-Jamendo)

**Task:** Multi-label genre classification, 87 classes.

**Input requirements:** 16000 Hz mono; uses EffNet/MAEST embeddings.

**Output:** 87 probability scores including era tags (60s, 70s, etc.) and genre tags
(techno, ambient, house, hip-hop, etc.).

**DJ relevance:** Medium. Less granular than Discogs-EffNet for electronic music but useful
for broader genre categorisation.

---

### OpenL3

**Task:** Self-supervised audio embeddings (not classification).

**Input requirements:** 16000 Hz audio.

**Output variants:** 512-dim or 6144-dim embeddings × mel-128 or mel-256 bands.

**DJ relevance:** Low–Medium. General-purpose embeddings useful for track similarity but
the Discogs-EffNet embeddings are better for DJ library use cases.

---

### AudioSet-VGGish

**Task:** General audio embedding extraction.

**Input requirements:** 16000 Hz mono.

**Output:** VGGish embeddings.

**DJ relevance:** Low. General audio representation, not music-specific.

---

### Spleeter (Source Separation)

**Task:** Separate audio into stems (vocals, drums, bass, piano, other).

**Output variants:** 2-stem (vocals + accompaniment), 4-stem, 5-stem.

**DJ relevance:** Medium–High for sample creation; Low for library analysis. Potentially
useful for detecting vocal presence (compare vocal stem energy to original).

---

## Audio Loading and Preprocessing

### AudioLoader

Loads audio files with full codec support via FFmpeg. Returns stereo samples.

**Python name:** `essentia.standard.AudioLoader`

**Outputs:**
| Name | Type | Description |
|---|---|---|
| `audio` | vector_stereosample | stereo audio signal |
| `sampleRate` | real | actual sample rate of the file |
| `numberChannels` | integer | channel count |
| `md5` | string | MD5 checksum of raw audio (if computeMD5=True) |
| `bit_rate` | integer | bit rate as reported by decoder |
| `codec` | string | codec used (e.g., 'mp3', 'flac') |

**Config params:**
| Param | Type | Default |
|---|---|---|
| `filename` | string | required |
| `audioStream` | integer | 0 |
| `computeMD5` | bool | false |

**Supported formats:** All FFmpeg-supported formats — wav, aiff, flac, ogg, mp3, mp4/m4a,
aac, opus, and more.

**Known issue:** OGG files are decoded in reverse phase due to FFmpeg behaviour.

**Windows note:** Filenames must be UTF-8 encoded on Windows.

---

### MonoLoader

Loads audio and downmixes to mono in one step. Resamples to target sample rate.

**Python name:** `essentia.standard.MonoLoader`

**Outputs:** `audio` (vector_real) — mono audio signal

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `filename` | string | required | |
| `sampleRate` | real | 44100 | target output sample rate Hz |
| `downmix` | string | mix | {left, right, mix} — how to downmix stereo |
| `audioStream` | integer | 0 | |
| `resampleQuality` | integer | 1 | [0, 4]; 0=best quality, 4=fastest |

**Formats:** Inherits AudioLoader support (all FFmpeg formats).

**For Crate:** This is the primary loader for all Essentia analysis (except LoudnessEBUR128
which needs stereo). Use `sampleRate=44100` for most algorithms; override to 16000 for ML
models and 11025 for TempoCNN.

---

### EasyLoader

Like MonoLoader but with additional ReplayGain normalisation and time slicing.

**Python name:** `essentia.standard.EasyLoader`

**Outputs:** `audio` (vector_real) — normalised mono audio signal

**Config params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `filename` | string | required | |
| `sampleRate` | real | 44100 | Hz |
| `downmix` | string | mix | {left, right, mix} |
| `replayGain` | real | -6 | dB normalisation level |
| `startTime` | real | 0 | seconds |
| `endTime` | real | 1e6 | seconds |
| `audioStream` | integer | 0 | |

---

## Derived Features

These are not direct Essentia outputs but must be computed from Essentia outputs. Listed
here as a design reference for the import pipeline.

### beat_regularity

How consistent the beat intervals are. 1.0 = perfectly regular; lower = more variable.

```python
# From RhythmExtractor2013 bpmIntervals output
import numpy as np
if len(bpm_intervals) > 1:
    beat_regularity = 1.0 - (np.std(bpm_intervals) / np.mean(bpm_intervals))
else:
    beat_regularity = None
```

**Status:** Reasonable formula. Needs validation against real tracks. A value around
0.9+ is expected for most techno/house. Below 0.7 likely indicates a poorly tracked or
live recording.

---

### intro_length / outro_length

Bars before/after energy crosses 50% of track mean. Not a direct Essentia output.

**Approach:** Use the `momentaryLoudness` time series from LoudnessEBUR128 or compute
an RMS envelope frame-by-frame. Then:

```python
import numpy as np

# energy_envelope: array of per-frame energy values (e.g. RMS per frame)
threshold = 0.5 * np.mean(energy_envelope)

# intro: bars before energy first crosses threshold
intro_frames = np.argmax(energy_envelope > threshold)
intro_seconds = intro_frames * hop_size / sample_rate
intro_bars = intro_seconds * (bpm / 60) / 4  # assuming 4/4 time

# outro: bars after energy last exceeds threshold
outro_frames = len(energy_envelope) - np.argmax(energy_envelope[::-1] > threshold) - 1
outro_seconds = (len(energy_envelope) - outro_frames) * hop_size / sample_rate
outro_bars = outro_seconds * (bpm / 60) / 4
```

**Status:** Formula is provisional. Needs validation on real tracks. The "50% of mean"
threshold is a reasonable starting point but may produce wrong results on tracks that
start loud immediately (no real intro) or have breakdown sections.

---

### energy_score, darkness_score, groove_score

These are entirely custom derived scores mentioned in CLAUDE.md. They are not computed by
Essentia. They must be designed based on combinations of Essentia outputs, then validated.
See CLAUDE.md Open Decisions — these are explicitly deferred until Phase 1 validation.

Candidate inputs:
- `energy_score`: integratedLoudness (LoudnessEBUR128), spectral_energyband_high, bpm
- `darkness_score`: SpectralCentroidTime centroid (Hz), spectral_rolloff, sub-bass EnergyBandRatio
- `groove_score`: beat_regularity, danceability, bpm histogram peak weight

---

### vocal_presence

Not a direct output. Must be derived from PredominantPitchMelodia:

```python
pitch, pitch_confidence = predominant_pitch_melodia(audio)
voiced_frames = pitch > 0
vocal_presence = float(np.mean(pitch_confidence[voiced_frames])) if voiced_frames.any() else 0.0
```

**Range:** [0, 1] — 0 = no detected pitch (likely instrumental), 1 = high-confidence
melodic content throughout. For typical techno this should be near 0.

---

## CLAUDE.md Claims — Verified and Corrected

| CLAUDE.md claim | Actual Essentia output | Status |
|---|---|---|
| `RhythmExtractor2013` → `bpm` | `bpm` (real, bpm) | Correct |
| `RhythmExtractor2013` → `bpm_confidence` | `confidence` (real, [0, 5.32]) | **Field name wrong** — actual: `confidence` not `bpm_confidence`. Also the range is 0–5.32, not 0–1. |
| `RhythmExtractor2013` → `beat_ticks` | `ticks` (vector_real, seconds) | **Field name wrong** — actual: `ticks` not `beat_ticks` |
| `RhythmExtractor2013` → `bpm_intervals` | `bpmIntervals` (vector_real, seconds) | Correct concept; Python camelCase is `bpmIntervals` |
| `KeyExtractor (edma)` → `key` | `key` (string) | Correct |
| `KeyExtractor (edma)` → `key_scale` | `scale` (string) | **Field name wrong** — actual: `scale` not `key_scale` |
| `KeyExtractor (edma)` → `key_strength` | `strength` (real) | **Field name wrong** — actual: `strength` not `key_strength` |
| `LoudnessEBUR128` → `loudness_lufs` (integrated) | `integratedLoudness` (real, LUFS) | **Field name wrong** — actual: `integratedLoudness` |
| `LoudnessEBUR128` → `dynamic_range` (LRA) | `loudnessRange` (real, LU) | **Field name wrong** — actual: `loudnessRange` |
| `SpectralCentroidTime` → `spectral_centroid (mean across frames, 0–1)` | `centroid` (real, **Hz**) | **Two errors**: field name wrong (actual: `centroid`) AND value range wrong (output is in Hz, not 0–1). This is significant for schema design. |
| `EnergyBandRatio` → `sub_bass_energy (20–100Hz)` | no such named field | **Not a named field** — must instantiate two separate EnergyBandRatio algorithms; each has one output `energyBandRatio` |
| `EnergyBandRatio` → `high_freq_energy (8kHz+)` | no such named field | Same as above |
| `PredominantPitchMelodia` → `vocal_presence (mean confidence, 0–1)` | `pitch` (vector_real, Hz) + `pitchConfidence` (vector_real, [0,1]) | **Not a direct output** — `vocal_presence` is a derived metric computed from both outputs |

**Summary:** Several field names in CLAUDE.md are wrong (using assumed snake_case names
instead of actual Essentia camelCase names). The SpectralCentroidTime range is fundamentally
wrong (Hz not [0, 1]). The EnergyBandRatio and PredominantPitchMelodia descriptions are
conceptually right but misrepresent how the API works.

---

## Installation

### For Linux (recommended path for Crate development)

```bash
# Using uv (as per Crate project standard)
uv add essentia

# Or with tensorflow support (for ML models)
uv add essentia-tensorflow
# Note: essentia and essentia-tensorflow conflict — install only one
```

**Supported Python versions and platforms (pip wheels):**
- Linux x86_64 and i686
- Python 3.8 through 3.11 (confirm current wheel availability at PyPI)
- macOS wheels may be available via conda-forge

**OS-level dependencies (if building from source on Ubuntu/Debian):**
```bash
sudo apt-get install build-essential libeigen3-dev libyaml-dev libfftw3-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswresample-dev \
  libsamplerate0-dev libtag1-dev libchromaprint-dev \
  python3-dev python3-numpy-dev python3-numpy python3-yaml python3-six
```

### Windows (WSL — required for Python bindings)

Python bindings are **not supported on native Windows**. Options:

1. **WSL2 (recommended for development):**
   ```bash
   # Inside WSL2 Ubuntu
   uv add essentia
   ```

2. **Docker:**
   ```bash
   docker pull mtgupf/essentia
   docker run -v /path/to/music:/music mtgupf/essentia \
     essentia_streaming_extractor_music /music/track.mp3 /tmp/features.json
   ```

3. **Cross-compile C++ only** (no Python, not suitable for Crate).

**Crate decision needed:** The development machine runs Windows 10. The backend must run in
WSL2 or Docker for Essentia to work. This should be documented in CURRENT_STATE.md and
confirmed before starting Phase 2.

### macOS

```bash
# Conda (easiest)
conda install -c conda-forge essentia

# Or build from source after:
brew install eigen libyaml fftw libsamplerate libtag chromaprint
brew install python --framework
```

### Verification script

```python
# verify_essentia.py — run after installation to confirm everything works
import essentia
import essentia.standard as es
import numpy as np

print(f"Essentia version: {essentia.__version__}")

# Test MonoLoader and RhythmExtractor2013 with a 5-second sine wave
sample_rate = 44100
duration = 5  # seconds
t = np.linspace(0, duration, sample_rate * duration)
audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)

rhythm = es.RhythmExtractor2013(method='multifeature', minTempo=100, maxTempo=160)
bpm, ticks, confidence, estimates, bpm_intervals = rhythm(audio)
print(f"BPM (sine wave, expect ~0 or garbage): {bpm}")
print(f"Confidence: {confidence}")

key_extractor = es.KeyExtractor(profileType='edma')
key, scale, strength = key_extractor(audio)
print(f"Key: {key} {scale}, strength: {strength}")

loudness_algo = es.LoudnessEBUR128()
stereo = es.StereoMuxer()(audio, audio)
momentary, short_term, integrated, loudness_range = loudness_algo(stereo)
print(f"Integrated loudness: {integrated:.1f} LUFS")
print(f"Loudness range: {loudness_range:.1f} LU")

print("All checks passed.")
```

---

## Performance

No official benchmarks from MTG documentation. Based on community reports and algorithm
characteristics:

| Operation | Estimated time (5-minute track) | Notes |
|---|---|---|
| MonoLoader (file read + resample) | 0.5–2 s | Depends on codec and disk speed |
| RhythmExtractor2013 (multifeature) | 5–15 s | CPU-intensive; the slowest standard algorithm |
| KeyExtractor | 1–3 s | Moderate |
| LoudnessEBUR128 | 1–2 s | Fast |
| PredominantPitchMelodia | 10–30 s | Very slow — consider skipping for non-vocal tracks |
| MFCC (per-frame) | 2–5 s | Moderate |
| Full analysis pipeline (all above) | 20–60 s | Per track |
| ML genre classification (EffNet) | 5–15 s | Requires essentia-tensorflow |

**Thread safety:** Essentia is **not fully thread-safe**. As noted in CLAUDE.md, use
`ThreadPoolExecutor` with `workers=2` at most. Do not share algorithm instances across
threads — instantiate separate algorithm objects per worker.

**Memory:** No official figures. Typical consumption for a full analysis pipeline on a
5-minute track at 44100 Hz is approximately 200–500 MB peak (audio loaded into memory
plus internal buffers). Keep this in mind if processing many tracks concurrently.

**Sample rate handling:** MonoLoader handles resampling automatically. However, running
algorithms at the wrong sample rate does not raise an error — RhythmExtractor2013 and
BeatTrackerMultiFeature produce incorrect results silently if given non-44100 Hz input.
Always verify sample rate before passing to these algorithms.

---

## Open Questions

These should be confirmed during Phase 2 validation on real tracks:

1. **SpectralCentroidTime Hz range on real techno tracks.** We know the output is in Hz.
   What is the practical range? Expected 500–5000 Hz. Needs measurement on a sample of 50
   tracks to establish normalisation bounds for the database.

2. **RhythmExtractor2013 confidence on electronic music.** The [0, 5.32] range comes from
   BeatTrackerMultiFeature. When using `method='multifeature'`, what confidence scores are
   typical for a straight-tempo techno track? Expected >3.5 (excellent) for most electronic
   music. Confirm threshold for flagging "needs manual BPM review".

3. **PredominantPitchMelodia on instrumental tracks.** Does the `pitch` output return all
   zeros for a purely instrumental track, or does it pitch-track the synth melody? If it
   tracks synths, the `vocal_presence` derivation above is invalid. Test on 10 vocal and
   10 instrumental tracks.

4. **KeyExtractor 'edma' vs 'bgate' on techno.** CLAUDE.md recommends 'edma'. Is it
   measurably better than 'bgate' for atonal techno? Test on 20 tracks with known keys.

5. **Danceability scale calibration.** The range is [0, ~3] but the documentation says
   "normal values". What is the distribution on a techno library? Are values above 2.0
   meaningful or artefacts?

6. **LoudnessEBUR128 on short tracks or intro-heavy tracks.** The integrated loudness uses
   gating which ignores silence. Does this work correctly on a 30-second intro that is
   mostly silence followed by a loud drop?

7. **Thread safety in practice.** The CLAUDE.md note says `workers=2`. Is 2 the actual
   safe limit, or can we use more with per-thread algorithm instances? Needs testing.

8. **Windows / WSL latency.** The development machine is Windows 10. If running Essentia
   in WSL2, the music files are likely on the Windows filesystem (mounted at /mnt/c/ or
   /mnt/d/). Cross-filesystem I/O in WSL2 is slow. This may significantly affect import
   performance. Needs measurement.

9. **essentia-tensorflow wheel availability on Python 3.11.** Confirm the PyPI wheel exists
   for Python 3.11 before committing to that Python version. If not available, may need to
   use Python 3.10.

10. **intro_length / outro_length formula accuracy.** The "50% of mean energy" threshold
    needs testing on real tracks. A track that starts at full energy with no intro would
    have intro_length = 0, which is correct, but what about a track with a gradual fade-in
    that crosses 50% at bar 4 of a 16-bar intro?
