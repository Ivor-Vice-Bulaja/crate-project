# backend/importer/

The import pipeline. Processes a single audio file through all data-enrichment steps.

## What belongs here

- `pipeline.py` — Orchestrates all steps in order. Steps 3–5 (network) run concurrently with step 6 (CPU).
- `tags.py` — Reads file tags using mutagen (title, artist, album, bpm, etc.)
- `acoustid.py` — Fingerprints the audio and queries the AcoustID service for a recording ID.
- `musicbrainz.py` — Fetches full metadata from MusicBrainz using the recording ID.
- `discogs.py` — Enriches label/catalogue data via the Discogs API.
- `essentia_analysis.py` — Runs Essentia audio analysis (BPM, key, loudness, spectral features).
- `embeddings.py` — Generates sentence-transformer embeddings and writes them to sqlite-vec.

## Pipeline order

```
1. Hash check → skip if unchanged
2. File tags (mutagen)
3. AcoustID fingerprint + query     ┐ concurrent
4. MusicBrainz metadata fetch       │ (ThreadPoolExecutor, workers=2)
5. Discogs enrichment               ┘
6. Essentia audio analysis (CPU-bound, ~5–15s)
7. Derive scores from Essentia outputs
8. Write to DB (INSERT OR REPLACE)
```
