# Task: Research Essentia as a Data Source

## Context

Read CLAUDE.md before starting. This task is Phase 1 research — no code is written here.
The goal is to produce a complete, accurate reference document that will be used to
finalise the database schema and the import pipeline in Phase 2.

Crate is a local DJ library application for techno and house DJs. Every track gets
analysed on import by a local audio analysis engine. We have chosen Essentia for this.
We need to know exactly what Essentia can give us — from first principles, based on
its actual documentation and source — before we design anything around it.

**Do not rely on prior knowledge about Essentia. Research it fresh from the source.**
The authoritative sources are:
- Essentia documentation: https://essentia.upf.edu/documentation.html
- Essentia algorithm reference: https://essentia.upf.edu/reference/
- Essentia-TensorFlow models: https://essentia.upf.edu/models.html
- MTG GitHub: https://github.com/MTG/essentia

---

## What to research

### 1. What is Essentia — a brief orientation

Before diving into algorithms, establish:
- What Essentia actually is (C++ library, Python bindings, streaming vs standard mode)
- The difference between `essentia` and `essentia-tensorflow` packages
- Where the official algorithm reference lives and how to navigate it
- What "standard mode" vs "streaming mode" means and which we should use

### 2. Complete algorithm inventory for audio feature extraction

Go to the Essentia algorithm reference and find every algorithm that could produce
useful per-track features for a DJ library. Do not start from a pre-defined list —
discover what actually exists.

Organise your findings into these categories (add others if you find relevant ones):

**Rhythm and tempo**
What algorithms exist for BPM detection, beat tracking, tempo stability, and
danceability? For each: exact outputs with field names and types, value ranges,
configuration options, and any notes on accuracy for electronic music (100–160 BPM,
highly regular beats).

**Key and tonality**
What algorithms exist for musical key detection, scale, chroma, and harmonic content?
For each: outputs, key profile options (which profiles exist and which suit electronic
music), value ranges.

**Loudness and dynamics**
What algorithms exist for loudness measurement, dynamic range, and level analysis?
Include any that relate to broadcast standards (EBU R128/LUFS) if they exist.

**Spectral and timbral features**
What algorithms exist for spectral analysis, brightness, energy distribution across
frequency bands, timbre description (MFCC, etc.)? For each: outputs, configuration.

**Vocal and melodic content**
What algorithms exist for detecting vocal presence, predominant melody, or pitch?
Relevant for classifying vocal vs instrumental tracks.

**Structure and segmentation**
What algorithms exist for detecting track structure — intro, outro, sections,
onsets, energy envelope over time?

**Any other categories** found in the reference that seem relevant to a DJ library.

For each algorithm document:
- Exact Python name (e.g. `essentia.standard.RhythmExtractor2013`)
- All output fields with exact names, data types, and value ranges
- All configuration parameters and their defaults
- Input requirements (sample rate, mono/stereo, data type)
- Any known issues or limitations

### 3. Pre-trained ML models (Essentia-TensorFlow)

Go to https://essentia.upf.edu/models.html and document the complete list of
available pre-trained models.

For each model (or model family) document:
- Full model name and the task it performs
- Output format (class labels and probabilities, or embedding vector)
- Input requirements (sample rate, segment length, mono/stereo)
- Where to download the model file
- Whether it requires GPU or runs on CPU only
- Relevance to a techno/house DJ library — be specific about what it would tell us
  about a track and whether that information is useful

Pay particular attention to:
- Any genre or style classifiers trained on electronic music
- Mood or energy classifiers
- Vocal/instrumental detectors
- Embedding models suitable for similarity search

### 4. Audio loading and preprocessing

Document how Essentia loads audio files:
- What loader classes exist (find them in the algorithm reference)
- What audio formats are supported natively
- How sample rate conversion works
- How mono/stereo is handled
- Any limitations with file length or format

### 5. What we can derive

Based on what you find Essentia actually outputs, identify:
- Which raw outputs could be combined to produce useful derived features for a DJ
  (e.g. beat stability, energy profile over time, intro/outro detection)
- For each derived feature: what the inputs are, how the computation would work,
  and what the expected output range would be
- Any features a DJ would want that Essentia cannot provide at all

Do not start from the derived features listed in CLAUDE.md. Discover what is possible
from the raw outputs and reason up from there. After completing your research,
compare your findings against the CLAUDE.md Essentia section and note any discrepancies.

### 6. Installation

Document the correct installation procedure:
- `essentia` vs `essentia-tensorflow` — exact pip/uv install commands
- Any OS-level dependencies required
- Known installation issues on Windows, macOS, Linux
- A minimal Python script that verifies the installation works

### 7. Performance on consumer hardware

Document what is known about:
- Processing time per track (look for benchmarks or community reports)
- Memory usage
- Thread safety — what can and cannot be parallelised safely
- CPU-only operation for the TensorFlow models

---

## Output format

Write your findings as a single Markdown document saved to:

```
docs/research/essentia.md
```

Structure it as follows:

```
# Essentia Research

## Sources
Links to every page you consulted, so findings can be verified.

## What Essentia Is
Brief orientation: packages, modes, where the reference lives.

## Algorithm Reference
One subsection per algorithm or algorithm family. For each:
exact Python name, all outputs (field name, type, range), all config params,
input requirements, limitations.

## ML Models Reference
One subsection per model or model family. For each:
task, outputs, input requirements, download location, CPU/GPU, DJ relevance.

## Audio Loading and Preprocessing
Loaders, formats, sample rate handling, mono/stereo.

## Derived Features
What can be derived from the raw outputs, with computation notes and expected ranges.
Discrepancies with CLAUDE.md noted explicitly.

## Installation
Step-by-step, verified for Python 3.11 and uv.

## Performance
Processing times, memory, thread safety.

## Open Questions
Anything that could not be confirmed from documentation alone and needs
a real test on audio files in Phase 2.
```

---

## Definition of done

- [ ] `docs/research/essentia.md` exists and is written from primary sources
- [ ] The algorithm reference section covers every algorithm found, not just a pre-selected list
- [ ] Every algorithm output is documented with its exact field name, type, and value range
- [ ] The ML models section covers every model on the Essentia models page
- [ ] Derived features are reasoned up from actual outputs, not assumed
- [ ] Discrepancies with CLAUDE.md are explicitly noted
- [ ] Installation instructions are specific to Python 3.11 and uv
- [ ] All sources are linked so findings can be verified
- [ ] Open questions are listed so they can be answered by running real tests in Phase 2
