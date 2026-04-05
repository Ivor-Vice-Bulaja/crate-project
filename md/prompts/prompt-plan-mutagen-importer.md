# Task: Plan the mutagen Tag Reader Module

## Context

Read CLAUDE.md before starting. This is a planning task — no code is written here.
The output is a detailed implementation plan that will be used to build
`backend/importer/tags.py` in Phase 2.

The research for this plan is complete. All mutagen API details, exact field access
patterns, ID3 frame names, format-specific differences, DJ software tag behaviour,
and edge cases are documented in `md/research/mutagen.md`. Read that document in full
before producing any plan — do not rely on prior knowledge about mutagen or audio tags.

**Core principle:** This module opens an audio file with mutagen and returns a flat
dictionary of raw tag values and audio properties. It does not score, rank, derive,
or normalise anything — it stores what mutagen gives us and lets later stages decide
what to do with it. The goal is to lose as little information as possible from the
file while never crashing on bad or missing data.

---

## What to plan

Design the implementation of `backend/importer/tags.py` — the module that takes a
file path and returns a flat dictionary of raw tag values and audio stream properties
ready to be written to the SQLite database.

### 1. Module interface

Define the exact function signature and return type. The function will be called from
`backend/importer/pipeline.py` as the first step before any network calls are made.

- What does the function take as input? (file path as string or Path object)
- What does it return on success? (flat dict of raw fields)
- What does it return when the file is not a recognised audio format?
- What does it return when the file exists but has no tags (`.tags` is None)?
- What does it return on a MutagenError (corrupt file, file access error)?
- Should errors be raised or returned as structured data?

The function must never raise — the pipeline must continue even if tag reading fails.
Define the error return dict shape.

### 2. Format detection and dispatch

mutagen.File() returns a different object depending on the file format, and tag access
patterns differ between ID3-based formats (MP3, AIFF, WAV), VorbisComment formats
(FLAC, OGG), and MP4. Specify:

- How the module detects which format was loaded (type check vs isinstance vs attribute check)
- Whether a single unified extraction function handles all formats or whether dispatch
  to format-specific helpers is used — make a concrete decision and justify it
- How to handle the WAV case specifically: WAV files may have `tags = None` even
  though they are valid audio (RIFF INFO chunks are not read by mutagen; ID3 chunk
  may be absent)
- How to handle `mutagen.File()` returning `None` (unrecognised format)
- Whether OGG formats are in scope for Phase 2 or deferred

### 3. Tag field extraction — ID3 (MP3, AIFF, WAV)

Specify the extraction logic for every field listed in the output schema (section 5).
For each ID3-sourced field:

- Which frame ID to access (e.g. `TIT2`, `TPE1`, `TBPM`)
- How to get the string value from the frame object (`.text[0]`, `str()`, etc.)
- How to handle frames with multiple values (e.g. multiple `TPE1` entries)
- How to handle the TYER vs TDRC duality for year/date:
  - Check `TDRC` first (ID3v2.4); fall back to `TYER` (ID3v2.3)
  - Store both raw values separately in the output dict so nothing is lost
- How to handle TXXX frames with DJ-software-written descriptions:
  - `TXXX:CATALOGNUMBER` / `TXXX:CATALOGID` — catalogue number
  - `TXXX:INITIALKEY` — key written by Mixed In Key and some others
  - `TXXX:ENERGY` — energy level written by some tools
  - Specify whether to use `.getall("TXXX")` and iterate, or direct key access, and why
- How to handle TCON numeric genre codes (e.g. `"(17)"`) — store raw, do not translate
- How to handle the `TRCK` track number field that may contain `"3/12"` — store raw

### 4. Tag field extraction — FLAC / OGG (VorbisComment)

For VorbisComment-based formats:

- How to access fields: `audio.get("TITLE", [None])[0]` pattern
- Which VorbisComment keys to read and map to which output dict keys
  (use the field mapping from the output schema in section 5)
- How to handle multi-value fields (e.g. two ARTIST values) — join as a string,
  store first only, or store as list? Make a concrete decision
- FLAC-specific: how to read `.pictures` (separate from `.tags`) for cover art
  detection without loading image bytes into memory

### 5. Tag field extraction — MP4 (M4A)

For MP4/iTunes atom-based formats:

- How to access text atoms: `audio.get("©nam", [None])[0]` pattern
- How to handle the `trkn` atom which returns `[(track_int, total_int)]` not a string
- How to handle the `tmpo` atom which returns `[int]` not a string
- Which MP4 atom keys to read and map to which output dict keys
- How to handle `©day` for year — may contain full ISO date or just a year

### 6. Audio stream properties extraction

For every supported format, specify extraction of audio stream properties from
`audio.info`. These are always present for valid audio files.

- `length` (float, seconds) — always present
- `bitrate` (int, bits per second) — always present
- `sample_rate` (int, Hz) — always present
- `channels` (int) — always present
- `bits_per_sample` (int) — present on FLAC, AIFF, WAV, M4A; absent on MP3 and OGG;
  specify how to handle the absent case (store None, do not attempt access)
- MP3-specific: `bitrate_mode` (CBR/VBR/ABR), `encoder_info`, `sketchy` — specify
  whether to store these or discard them
- Format identifier: store the detected format as a string (e.g. `"mp3"`, `"flac"`,
  `"aiff"`, `"wav"`, `"m4a"`) so the pipeline knows what it received

### 7. Cover art handling

The import pipeline does not store cover art in Phase 2. However, the tags module
should detect whether cover art is present and record that as a boolean flag, so
the pipeline can later fetch cover art separately if needed.

Specify:
- How to detect cover art presence for ID3 (check for APIC frame with type=3) without
  loading image bytes into memory
- How to detect cover art presence for FLAC (check `audio.pictures` list length)
- How to detect cover art presence for MP4 (check `covr` atom)
- What to store: a boolean `has_embedded_art`, not the image bytes themselves
- The single edge case to handle: APIC frame present but type ≠ 3 (e.g. artist photo,
  back cover) — should `has_embedded_art` be True or only when type=3 is present?
  Make a concrete decision.

### 8. GEOB and DJ software data

Serato, Rekordbox, and Traktor write proprietary binary data into GEOB frames and
TXXX frames. The research doc confirms:
- Serato BPM, beat grid, and cue points are in binary GEOB frames — not plain text
- Rekordbox cue points and beat grid are in binary GEOB frames — not plain text
- Traktor cue points are stored in the Traktor database, not in file tags

For the Phase 2 import pipeline, binary GEOB parsing is out of scope. Specify:

- Whether to record which DJ software has written to the file (detection only, no parsing)
  — for example, detect presence of `GEOB:Serato Analysis`, `GEOB:Serato Autotags`,
  `PRIV:TRAKTOR4`, and store as boolean flags `has_serato_tags`, `has_traktor_tags`,
  `has_rekordbox_tags`
- How to detect Rekordbox tags (the research doc does not confirm the exact GEOB
  description string — specify that detection is best-effort and may be an open question)
- Whether to read `TXXX:ENERGY` or `TXXX:INITIALKEY` written by DJ software as plain
  text (these are accessible without binary parsing)

### 9. Output schema

Define the complete return dictionary. For every key:
- Key name (snake_case)
- Source: frame ID / atom key / audio.info attribute / derived
- Python type after extraction
- Nullable? (and when)

The plan must include at minimum:

```
# File identity
file_path           str     os.fspath(path)                     always set
file_format         str     detected format ("mp3","flac",...)  always set
file_hash           None    NOT computed by this module — pipeline responsibility

# Audio stream properties
duration_seconds    float   audio.info.length                   always set
bitrate_bps         int     audio.info.bitrate                  always set
bitrate_mode        str     audio.info.bitrate_mode.name        MP3 only, else None
sample_rate_hz      int     audio.info.sample_rate              always set
channels            int     audio.info.channels                 always set
bits_per_sample     int     audio.info.bits_per_sample          FLAC/AIFF/WAV/M4A, else None
encoder_info        str     audio.info.encoder_info             MP3 only, else None
is_sketchy          bool    audio.info.sketchy                  MP3 only, else None

# Core text fields
tag_title           str     TIT2 / TITLE / ©nam                 None if absent
tag_artist          str     TPE1 / ARTIST / ©ART                None if absent
tag_album_artist    str     TPE2 / ALBUMARTIST / aART           None if absent
tag_album           str     TALB / ALBUM / ©alb                 None if absent
tag_label           str     TPUB / ORGANIZATION / ©pub          None if absent
tag_catalogue_no    str     TXXX:CATALOGNUMBER or TXXX:CATALOGID / CATALOGNUMBER  None if absent
tag_genre           str     TCON / GENRE / ©gen                 None if absent; raw including "(17)" codes
tag_comment         str     COMM / COMMENT / ©cmt               None if absent; first COMM frame only
tag_isrc            str     TSRC / ISRC                         None if absent
tag_copyright       str     TCOP / COPYRIGHT / cprt             None if absent

# Date / year (store both raw ID3 fields to avoid losing data)
tag_year_id3v24     str     TDRC text[0]                        None if absent (v2.4 timestamp)
tag_year_id3v23     str     TYER text[0]                        None if absent (v2.3 4-digit year)
tag_date_released   str     TDRL text[0]                        None if absent
tag_date_original   str     TDOR / TORY                         None if absent
tag_date_vorbis     str     DATE (VorbisComment)                None if absent (FLAC/OGG)
tag_date_mp4        str     ©day                                None if absent (M4A)

# Track / disc numbering
tag_track_number    str     TRCK / TRACKNUMBER / trkn           None if absent; raw "3/12" preserved
tag_disc_number     str     TPOS / DISCNUMBER / disk            None if absent

# DJ-relevant fields
tag_bpm             str     TBPM / BPM / tmpo                   None if absent; raw string
tag_key             str     TKEY / INITIALKEY                   None if absent; notation not normalised
tag_energy          str     TXXX:ENERGY / ENERGY                None if absent
tag_initial_key_txxx str    TXXX:INITIALKEY                     None if absent (separate from TKEY)

# Cover art detection
has_embedded_art    bool    presence of APIC type=3 / pictures / covr    False if absent

# DJ software detection (presence flags only — no binary parsing)
has_serato_tags     bool    presence of GEOB:Serato Analysis            False if absent
has_traktor_tags    bool    presence of PRIV:TRAKTOR4                   False if absent
has_rekordbox_tags  bool    presence of Rekordbox GEOB frame            False if absent; best-effort

# Tag metadata
tag_id3_version     str     e.g. "2.3.0" from audio.tags.version        None for non-ID3 formats
tag_format_type     str     "id3" / "vorbiscomment" / "mp4" / "none"    always set

# Error / status
tags_error          str     error description if tags could not be read  None on success
tags_present        bool    whether audio.tags is not None              always set
```

For `tag_bpm`: MP3 stores it as a string in TBPM, OGG/FLAC as a string in BPM, M4A
as an integer in `tmpo` — specify how `tmpo`'s integer value is stored (convert to
string for consistency, or store as int and accept the type difference).

For `tag_comment`: COMM frames have a language field and a description field. Multiple
COMM frames can exist. Specify which to read (first with empty description, or first
overall) and whether to store the language field separately.

### 10. Error handling

The module must never raise an exception to the caller. Define the complete error contract:

- **`mutagen.File()` returns `None`**: format not recognised. Return dict with all tag
  fields as None, `file_format = "unknown"`, `tags_present = False`,
  `tags_error = "unrecognised format"`. Audio properties fields also None.
- **`mutagen.MutagenError`** (corrupt tag, file truncated, IO error): catch, log at
  WARNING, return dict with `tags_error` set to exception message, tag fields as None,
  audio properties as None where unavailable.
- **`mutagen.id3.ID3NoHeaderError`**: only raised when using `ID3()` directly — this
  module uses `mutagen.File()`, so this is not expected. Document that it is not caught
  separately.
- **`audio.tags` is None** (valid audio, no tag block): return dict with tag fields as
  None, `tags_present = False`, `tags_error = None`, audio properties populated. This
  is normal and not an error.
- **KeyError on individual frame access** (expected frame absent): do not use bare key
  access; use `.get()` or try/except per field. Individual missing fields return None.
- **Top-level fallback**: wrap the entire function body in a try/except to guarantee
  a dict is always returned. Log unexpected exceptions at ERROR level.

Define what the error dict looks like: which fields are set, which are None, and what
`tags_error` contains in each case.

### 11. Memory considerations

The research doc notes that loading large APIC frames into memory during a batch
import of thousands of tracks can consume significant memory (~500 MB for 1,000 tracks
with 500 KB cover art each). Since the module is not storing image bytes, specify:

- Whether `audio.tags.getall("APIC")` is called and image bytes are briefly held in
  memory for the cover art presence check, or whether the check avoids loading bytes
- Whether there is a pattern in mutagen to check for frame presence without loading
  frame data (check if this is possible from the research doc; if not, note it as an
  open question)
- The recommended approach for a batch import pipeline (accept the memory cost,
  or only check frame key presence using `"APIC:..." in audio.tags`)

### 12. Configuration

Identify every value that should not be hardcoded:
- Whether to attempt TXXX field reads at all (some libraries have many TXXX frames)
- Whether to detect DJ software tags (adds overhead)
- Which file extensions to accept as valid input (or defer format detection entirely
  to mutagen.File's header-based detection)

Most of these have sensible fixed defaults for Phase 2. Specify which (if any) belong
in `backend/config.py` vs hardcoded constants in the module.

### 13. Test plan

Describe the tests for `backend/tests/test_importer/test_tags.py`:

**No real audio files required in tests.** All mutagen interactions are mocked.
Use `unittest.mock.patch("mutagen.File")` to control what the module sees.

- **Fixture strategy**: define minimal mock objects for MP3Info, VComment, MP4Tags,
  ID3 tags — enough attributes to satisfy the extractor without loading real files
- **Happy path tests:**
  - MP3 with full ID3v2.4 tags → all fields populated correctly
  - MP3 with ID3v2.3 TYER only (no TDRC) → tag_year_id3v23 populated, tag_year_id3v24 None
  - FLAC with VorbisComment → VorbisComment fields mapped to correct output keys
  - M4A with MP4 atoms → trkn tuple converted correctly, tmpo int stored correctly
  - AIFF → ID3 tags accessed same as MP3, bits_per_sample present
  - WAV with ID3 chunk → tags read correctly
  - WAV without ID3 chunk (tags=None) → tags_present=False, audio properties present
- **Edge case tests:**
  - mutagen.File() returns None → error dict returned, no exception propagated
  - MutagenError raised → error dict with tags_error set, no exception propagated
  - All tag fields absent (no TIT2, no TPE1, etc.) → all tag_* fields None
  - TBPM contains "128.00" (decimal string) → stored as-is, not converted to int
  - TCON contains "(17)" → stored as raw string "(17)"
  - TRCK contains "3/12" → stored as raw string "3/12"
  - TXXX:CATALOGNUMBER present → tag_catalogue_no populated
  - TXXX:CATALOGID present (alternate casing) → tag_catalogue_no populated
  - TKEY and TXXX:INITIALKEY both present → both stored in separate output fields
  - has_embedded_art True when APIC type=3 present
  - has_embedded_art False when APIC type=4 (back cover) present but no type=3
  - has_serato_tags True when GEOB:Serato Analysis frame present
- **MP3-specific tests:**
  - bitrate_mode CBR → stored as "CBR"
  - sketchy=True → is_sketchy=True
  - encoder_info present → encoder_info populated
- **Top-level fallback test:**
  - Unexpected exception inside extractor → error dict returned, no exception propagated

### 14. Open questions from the research doc

`md/research/mutagen.md` lists 10 open questions. For each one that affects this module,
state whether it blocks the implementation plan or can be deferred, and what the
interim decision is.

Key questions to address:

- **Catalogue number field name in FLAC** (OQ1): the research doc notes uncertainty
  about whether `CATALOGNUMBER`, `LABELNO`, or `LABEL_NUMBER` is the correct VorbisComment
  key. Interim decision: read `CATALOGNUMBER` as primary, note that LABELNO is unconfirmed,
  treat as an open question for Phase 2 validation on real files.

- **Beatport TKEY notation in FLAC** (OQ2): uncertain whether Beatport FLAC uses
  `INITIALKEY` or `BPM` as the VorbisComment key for key. Interim decision: read both
  `INITIALKEY` and `KEY` as potential sources, store raw, defer normalisation.

- **Serato TBPM vs GEOB BPM consistency** (OQ3): under what conditions does Serato
  write BPM to TBPM? Interim decision: read TBPM as the authoritative plain-text BPM
  source; binary GEOB parsing is deferred to Phase 2 validation.

- **Rekordbox TKEY notation** (OQ4): traditional ("A minor") vs abbreviated ("Am").
  Does not block implementation — store raw, normalise later.

- **TXXX:CATALOGNUMBER vs TXXX:CATALOGID** (OQ5): which description string is more
  common? Interim decision: check both, prefer CATALOGNUMBER, fall back to CATALOGID.

- **WAV RIFF INFO via Rekordbox USB export** (OQ6): confirmed that mutagen cannot read
  RIFF INFO. The module will return tags_present=False for these files. This is a known
  limitation; WAV files from Rekordbox USB exports will have no metadata from this module.

- **mutagen v2.3 save behaviour** (OQ8): irrelevant for a read-only pipeline (no
  `.save()` calls). Confirm in the plan that the module never calls `.save()`.

- **mutagen version currency** (OQ10): note that v1.47.0 is documented; check for
  newer releases before implementing.

---

## Output format

Write the plan as a single Markdown document saved to:

```
md/plans/mutagen-importer.md
```

Structure:

```
# Implementation Plan: mutagen Tag Reader Module

## Overview
One paragraph: what the module does, what it does not do.

## Function Interface
Exact signature, return type, error contract.

## Format Detection and Dispatch
How formats are detected, whether dispatch is unified or per-format.

## Tag Extraction — ID3 (MP3, AIFF, WAV)
Field-by-field extraction logic. TYER vs TDRC handling. TXXX handling.

## Tag Extraction — VorbisComment (FLAC, OGG)
Field-by-field extraction logic. Multi-value handling.

## Tag Extraction — MP4 (M4A)
Field-by-field extraction logic. trkn/tmpo type handling.

## Audio Properties Extraction
Per-format fields from audio.info. Format-specific differences.

## Cover Art Detection
Detection logic per format. Memory considerations.

## DJ Software Tag Detection
Which flags to set, which frames to look for.

## Output Schema
Full table: key | source | type | nullable

## Error Handling
Specific strategy for each failure mode.

## Memory Considerations
APIC frame loading strategy for batch imports.

## Configuration
Table: parameter | controls | location | default

## Test Plan
Fixtures, mock strategy, happy path, edge cases, error paths.

## Open Questions
Each relevant research question and interim decision.

## Implementation Order
Numbered steps to build this module in Phase 2.
```

---

## Definition of done

- [ ] `md/plans/mutagen-importer.md` exists
- [ ] Function interface specifies exact signature and error contract (never raises)
- [ ] Format detection specifies how to handle MP3, FLAC, AIFF, WAV, M4A, and the
      None return from mutagen.File()
- [ ] Tag extraction covers TYER vs TDRC duality for year/date
- [ ] Tag extraction covers TXXX field access for catalogue number, initial key, energy
- [ ] Output schema table covers every field listed in section 9
- [ ] No derived scores, normalised values, or computed fields anywhere in the plan —
      only raw values as mutagen returns them
- [ ] Cover art detection stores a boolean only — no image bytes in the output dict
- [ ] DJ software detection specifies boolean flags and which frames to check
- [ ] Error handling is specific for each failure mode (None return, MutagenError,
      tags=None, individual frame absence)
- [ ] Memory section addresses APIC frame loading for batch imports
- [ ] Test plan uses mocked mutagen — no real audio files required
- [ ] All open questions that affect the plan have a stated interim decision
- [ ] Implementation order is a concrete numbered list
