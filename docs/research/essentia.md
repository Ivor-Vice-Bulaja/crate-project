# Essentia — Research

Tested: 2026-04-05
Sample: 10 MP3 tracks from a techno/house DJ library (SEP2025 folder)
Script: `scripts/test_importers.py --essentia --essentia-count 10 --no-pitch --no-acoustid --no-discogs --no-cover-art`
Environment: WSL2, essentia 2.1-beta6-dev, Python 3.11
Timing: ~14s/track (without pitch, without ML models)

---

## What Essentia returns

### Rhythm

```
bpm                  float   — beats per minute (RhythmExtractor2013, method='multifeature')
bpm_confidence       float   — confidence score, range 0–5.32
beat_ticks           list    — beat positions in seconds
bpm_estimates        list    — per-beat BPM estimates (float array)
bpm_intervals        list    — inter-beat intervals in seconds
```

Configuration: `minTempo=100, maxTempo=160` for techno/house. Adjust for other genres.

### Danceability

```
danceability         float   — Essentia classical Danceability algorithm output
danceability_dfa     list    — DFA (Detrended Fluctuation Analysis) array
```

Note: this is the classical signal-based Danceability, not the ML danceability model.
Range is unbounded; higher is more danceable. The ML model (`ml_danceability`, 0–1) is
more calibrated but requires model files.

### Key & Tuning

```
key                  str     — musical key (e.g. "C", "Bb", "F#")
key_scale            str     — "major" or "minor"
key_strength         float   — confidence 0–1; higher = more tonal certainty
tuning_frequency_hz  float   — estimated tuning reference frequency (Hz; 440 = concert pitch)
tuning_cents         float   — deviation from 440 Hz in cents
```

Configuration: `profileType='edma'` for electronic music (KeyExtractor).

### Loudness

```
integrated_loudness      float   — overall loudness in LUFS (EBU R128)
loudness_range           float   — dynamic range in LU (EBU R128)
dynamic_complexity       float   — Essentia DynamicComplexity; measures amplitude variation
dynamic_complexity_loudness float — loudness level from DynamicComplexity
momentary_loudness       list    — 400ms window loudness values (frame array)
short_term_loudness      list    — 3s window loudness values (frame array)
```

`LoudnessEBUR128` requires stereo input. The importer muxes mono to stereo via `StereoMuxer`.

### Spectral

```
spectral_centroid_hz float   — mean spectral centroid across frames (Hz); typical range ~500–5000 Hz
sub_bass_ratio       float   — mean energy ratio in 20–100 Hz band (EnergyBandRatio)
high_freq_ratio      float   — mean energy ratio in 8000–22050 Hz band (EnergyBandRatio)
mfcc_mean            list    — 13-coefficient MFCC mean vector
mfcc_var             list    — 13-coefficient MFCC variance vector
bark_bands_mean      list    — 27-band Bark energy mean vector
```

SpectralCentroidTime output is in Hz (NOT normalised 0–1). See CLAUDE.md note on this.

### Onsets & Pitch

```
onset_rate           float   — onsets per second (OnsetRate)
onset_times          list    — onset positions in seconds

pitch_frames         list    — per-frame pitch in Hz (PredominantPitchMelodia); slow
pitch_confidence_frames list — per-frame pitch confidence 0–1
```

PredominantPitchMelodia is disabled by default (`--no-pitch`) — adds 10–30s/track.
`vocal_presence` must be derived as `mean(pitch_confidence_frames)` over voiced frames.

### ML models (require separate model downloads)

All ML outputs are `None` when model files are absent. No errors raised.

```
genre_probabilities      list    — 400-class Discogs-EffNet softmax output
genre_top_labels         list    — top N genre strings from EffNet
embedding                list    — 1280-dim EffNet track embedding
embedding_track          list    — 1280-dim track-level embedding variant
embedding_artist         list    — 1280-dim artist-level embedding variant
embedding_label          list    — 1280-dim label-level embedding variant
embedding_release        list    — 1280-dim release-level embedding variant
arousal                  float   — arousal score 0–1 (DEAM/MusiCNN)
valence                  float   — valence score 0–1 (DEAM/MusiCNN)
mood_aggressive          float   — probability 0–1 (Discogs-EffNet)
mood_happy               float   — probability 0–1
mood_party               float   — probability 0–1
mood_relaxed             float   — probability 0–1
mood_sad                 float   — probability 0–1
ml_danceability          float   — probability 0–1 (index 0 = "danceable")
instrument_probabilities list    — 40-class MTG-Jamendo instrument probabilities
instrument_top_labels    list    — top N instrument strings
moodtheme_probabilities  list    — 56-class MTG-Jamendo mood/theme probabilities
moodtheme_top_labels     list    — top N mood/theme strings
voice_probability        float   — 0 = instrumental, 1 = vocal (EffNet)
voice_probability_musicnn float  — same, MusiCNN variant
```

Model files required (place in `./models/`):
- `discogs-effnet-bs64-1.pb` + `.json` — genre + embeddings
- `deam-msd-musicnn-2.pb` — arousal/valence
- `msd-musicnn-1.pb` — MusiCNN backbone for DEAM and voice
- `mood_aggressive-discogs-effnet-1.pb` (and happy, party, relaxed, sad)
- `danceability-discogs-effnet-1.pb`
- `mtg_jamendo_instrument-discogs-effnet-1.pb` + `.json`
- `mtg_jamendo_moodtheme-discogs-effnet-1.pb` + `.json`
- `voice_instrumental-discogs-effnet-1.pb`
- `voice_instrumental-musicnn-msd-2.pb`
- `discogs_track_embeddings-effnet-bs64-1.pb` (and artist, label, release variants)

All available from the Essentia models repository.

### Metadata

```
essentia_version     str    — e.g. "2.1-beta6-dev"
analysis_timestamp   str    — ISO 8601 UTC
analysis_error       str    — only present on failure
```

---

## Field coverage — 10-track sample

All core algorithm outputs: **100%** (BPM, key, loudness, spectral, onsets, danceability,
tuning). ML outputs: 0% (no model files). Pitch: 0% (disabled). Zero errors.

---

## Real-data values — 10 techno/house tracks

**BPM:** min=123.8, max=144.3, avg=137.4  
Expected for this library. `minTempo=100, maxTempo=160` config is correct.

**Key distribution (10 tracks):** Bb minor ×2, B minor ×2, C major ×2, E major ×1,
E minor ×1, C# major ×1 — mixed, no single dominant key. Reasonable for a diverse sample.

**Integrated loudness:** min=-12.0, max=-7.6, avg=-8.6 LUFS  
Club tracks are typically mastered hot (-9 to -6 LUFS). This is consistent.
-12 LUFS outliers are likely tracks with extended quiet intros/outros pulling the average down.

---

## Performance

Without pitch analysis, without ML models:
- **~14s/track** on average over 10 tracks (WSL2 on Windows host, reading files from NTFS)
- The NTFS filesystem access via `/mnt/c/` adds overhead; native Linux storage would be faster
- RhythmExtractor2013 (`method='multifeature'`) is the slowest standard algorithm (~8s/track)

With pitch analysis enabled (`PredominantPitchMelodia`): adds ~10–30s/track.  
With ML models: adds ~20–60s/track depending on which models are loaded.

Implication for the import pipeline: Essentia should run in a background thread or process.
The `max_workers=2` ThreadPoolExecutor limit in the pipeline design is correct — Essentia
is not fully thread-safe; algorithm instances must not be shared across threads.

---

## Platform notes

- **Native Windows:** not supported — Essentia has no Windows wheels
- **WSL2:** confirmed working (essentia 2.1-beta6-dev, Python 3.11)
- **numpy<2 required:** essentia 2.1-beta6-dev uses `numpy.core` which was removed in NumPy 2.x.
  Pin with `numpy<2` in the venv. The `pyproject.toml` constraint `numpy>=1.26.0` allows NumPy 2
  which breaks essentia — this should be tightened to `numpy>=1.26.0,<2`.

---

## CUDA warning

On import, TensorFlow logs:  
`Could not load dynamic library 'libcudart.so.11.0'`  
This is harmless on CPU-only machines. Suppress by setting `TF_CPP_MIN_LOG_LEVEL=3`
in the environment if it clutters logs.
