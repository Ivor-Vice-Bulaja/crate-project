# Task: Research File Tags and mutagen as a Data Source

## Context

Read CLAUDE.md before starting. This task is Phase 1 research — no code is written here.
The goal is to produce a complete, accurate reference document that will be used to
finalise the database schema and the import pipeline in Phase 2.

Crate is a local DJ library application for techno and house DJs. Every track gets
enriched on import using multiple data sources. File tags are the first source — they
are read before any network call is made. We have chosen mutagen as the tag-reading
library. We need to know exactly what mutagen returns for every relevant audio format
before we design anything around it.

**Do not rely on prior knowledge about mutagen or audio tag formats. Research them fresh
from the source.** The authoritative sources are:
- mutagen documentation: https://mutagen.readthedocs.io/
- mutagen source on GitHub: https://github.com/quodlibet/mutagen
- ID3 standard (v2.3 and v2.4): https://id3.org/id3v2.3.0 and https://id3.org/id3v2.4.0
- Vorbis comment specification: https://wiki.xiph.org/VorbisComment
- MP4/iTunes metadata spec reference in mutagen docs

**Do not pre-filter what you document based on what you think the project needs.**
The goal is a complete picture of every tag field and audio property mutagen exposes.
What is useful for Crate will be decided after the research is complete, not during it.

---

## What to research

### 1. What mutagen is — orientation

Before touching the API, establish:
- What mutagen is — what the library does, who maintains it, what its scope is
- Which audio file formats it supports — enumerate all of them with their file extensions
- The difference between tag-level data (metadata written into the file) and
  audio-property-level data (bitrate, sample rate, duration — derived from the audio stream)
- How mutagen handles unknown or unsupported formats
- Maintenance status — is the library actively maintained, what Python versions are supported

### 2. Tag format landscape

DJ libraries predominantly contain MP3, FLAC, AIFF, WAV, and sometimes M4A/AAC and OGG.
For each of these formats, establish which tag format(s) it uses:

**ID3 (used by MP3 and AIFF)**
- What ID3v1 is — field list, character encoding limitations, why it is largely obsolete
- What ID3v2.3 is — frame-based structure, common frames, how mutagen exposes it
- What ID3v2.4 is — how it differs from v2.3, which is more common in DJ libraries
- Whether a file can contain both ID3v1 and ID3v2 simultaneously — how mutagen handles this
- How mutagen normalises ID3v2.3 vs v2.4 differences (if at all)

**Vorbis Comment (used by FLAC and OGG)**
- What Vorbis Comment is — key=value structure, character encoding (UTF-8 always)
- The standard field names defined by the spec — enumerate all of them
- How it differs from ID3 — no frame types, free-form keys, multiple values per key allowed

**MP4/iTunes tags (used by M4A/AAC)**
- What MP4 tags are — the iTunes atom-based structure
- How mutagen represents them — what keys look like (e.g. `©nam`, `©ART`)
- Standard fields available in MP4 tags

**RIFF INFO chunks (used by WAV)**
- Whether WAV files support embedded ID3 or use RIFF INFO chunks
- What RIFF INFO chunk keys look like
- How mutagen handles WAV tags — which format does it read/write for WAV

**APEv2 (sometimes found in MP3, used by WavPack, Musepack)**
- What APEv2 is — when it appears in a DJ library
- How it overlaps with or conflicts with ID3 tags in the same file

### 3. The mutagen Python API — all objects and methods

**Opening a file**
- `mutagen.File()` — what it returns, how it detects format, what happens on failure
- `easy=True` parameter — what EasyID3/EasyMP3 is, what it normalises, when to use it
- Whether mutagen can open a file when its extension is wrong or missing
- Return value when the file is not a recognised audio format

**The `FileType` base object**
- Every attribute and method on the base `FileType` object
- The `.tags` attribute — when it is `None` vs populated
- The `.info` attribute — what it contains (document every field on the `StreamInfo` object
  for MP3, FLAC, AIFF, WAV, M4A, and OGG separately)
- `.save()`, `.delete()`, `.add_tags()` — what each does

**ID3 API**
- `mutagen.id3.ID3` — how to open, what it contains
- `mutagen.mp3.MP3` — how it differs from `ID3`; how to access the ID3 tag vs audio info
- `mutagen.easyid3.EasyID3` and `mutagen.easymp3.EasyMP3` — the normalised key map;
  enumerate every key in the EasyID3 key map and what ID3 frame it maps to
- How to access raw ID3 frames directly — what `tags['TIT2']` returns vs `tags['TIT2'].text`
- How multi-value frames work (e.g. multiple artists in `TPE1`)
- Text encoding in ID3 frames — how mutagen exposes it, whether encoding affects the string value

**FLAC API**
- `mutagen.flac.FLAC` — what it returns
- How Vorbis Comment tags are accessed — key access, iteration
- The `.pictures` attribute on FLAC — what it contains (not just whether it exists — document
  every field on the `Picture` object)

**MP4 API**
- `mutagen.mp4.MP4` — what it returns
- How MP4 tag values differ from ID3 — type wrappers (`MP4FreeForm`, etc.), integer values,
  tuple values for track number
- Cover art in MP4 — how to access it, what type it comes back as

**WAV and AIFF APIs**
- `mutagen.wave.WAVE` and `mutagen.aiff.AIFF` — what each returns
- Whether WAV/AIFF tags are accessed the same way as MP3 ID3 tags or differently
- Known limitations for WAV tag support in mutagen

### 4. Standard ID3 frames — exhaustive documentation

This is the most important section for understanding what metadata a DJ file can contain.

Document every ID3 frame that is relevant to music metadata. For each frame:
- Frame ID (4-character code, e.g. `TIT2`)
- Human name
- Data type and structure
- Whether it appears as a single string, list of strings, or structured object in mutagen
- How common it is in DJ-library files

Cover all frame categories:
- **Text frames (T-frames)**: `TIT1`, `TIT2`, `TIT3`, `TALB`, `TPE1`, `TPE2`, `TPE3`,
  `TPE4`, `TCOM`, `TEXT`, `TOLY`, `TPUB`, `TCON`, `TRCK`, `TPOS`, `TYER`, `TDRC`,
  `TBPM`, `TKEY`, `TLEN`, `TSRC`, `TLAN`, `TCOP`, `TENC`, `TSSE`, `TSIZ`, `TFLT`,
  `TMED`, `TMOO`, `TCAT`, `TDES`, `TGID`, `WFED`, `TOWN`, `TOFN`, `TDLY`, `TDEN`,
  `TDOR`, `TDRL`, `TDTG`, `TSST`, `TSOP`, `TSOA`, `TSOT`, `TIPL`, `TMCL` —
  document every one of these that exists in the ID3 spec
- **Comment frames**: `COMM` — structure, language field, description field
- **URL frames**: `WCOM`, `WCOP`, `WOAF`, `WOAR`, `WOAS`, `WORS`, `WPAY`, `WPUB`
- **Unique file identifier**: `UFID` — what it stores, when it is used
- **Attached picture**: `APIC` — every field (mime_type, type, desc, data); all `PictureType`
  enum values
- **Lyrics**: `USLT` and `SYLT`
- **Chapters and table of contents**: `CHAP`, `CTOC`
- **Play counter and popularimeter**: `PCNT`, `POPM`
- **General encapsulated object**: `GEOB` — this is critical for DJ software data (document
  precisely what it stores and how mutagen exposes it)
- **Private frame**: `PRIV` — what it stores, how mutagen exposes it
- **User-defined text**: `TXXX` — how the description field distinguishes multiple TXXX frames;
  how mutagen keys them
- **User-defined URL**: `WXXX`
- **Seek frame and audio encryption**: `SEEK`, `AENC`

### 5. DJ software custom tags — exhaustive documentation

This is critical for Crate. DJ software writes proprietary metadata into audio files.
When a DJ has used Traktor, Rekordbox, Serato, or VirtualDJ, their files will contain
this data alongside standard tags.

For each application, document what tags it writes and how mutagen exposes them:

**Serato**
- What Serato writes into MP3 files — which frames (GEOB frames with specific descriptions,
  TXXX frames, etc.)
- Specifically: `GEOB:Serato Analysis`, `GEOB:Serato Autotags`, `GEOB:Serato BeatGrid`,
  `GEOB:Serato Markers_`, `GEOB:Serato Markers2`, `GEOB:Serato Offsets_`,
  `GEOB:Serato Overview`, `GEOB:Serato PlayTime`, `GEOB:Serato RelVol0`,
  `GEOB:Serato Video Associates`, `GEOB:Serato WhiteNoise` — for each, document what
  data it encodes (even if the format is binary/proprietary)
- What Serato writes into FLAC files — which Vorbis Comment keys
- What Serato writes into AIFF files
- Whether Serato BPM is stored in a standard `TBPM` frame or only in its own GEOB frames

**Rekordbox (Pioneer)**
- What Rekordbox writes into MP3 files — GEOB frames, TXXX frames, custom frames
- Specifically look for: beat grid data, cue points, memory cues, energy level,
  key analysis — where each is stored
- Whether Rekordbox writes a `TXXX:REKORDBOX_ANALYSIS_VERSION` or similar marker
- What Rekordbox writes into FLAC and AIFF files

**Traktor (Native Instruments)**
- What Traktor writes into MP3 files — GEOB frames, TXXX frames
- Whether Traktor stores cue points in the file or only in its own database

**VirtualDJ**
- What VirtualDJ writes into files — if anything

**Common TXXX fields used across DJ software**
- `TXXX:COMMENT`, `TXXX:ENERGY`, `TXXX:RATING`, `TXXX:BPM`, `TXXX:INITIALKEY` —
  document which software writes which TXXX frames

**What can be read without special parsing**
- Which of the above DJ software fields are accessible as plain strings via mutagen
  without needing to decode proprietary binary formats
- Which fields require custom binary parsing (and are therefore out of scope for a
  simple tag read pass)

### 6. Audio stream properties — what mutagen exposes

For each of MP3, FLAC, AIFF, WAV, M4A, and OGG, document every field on the `.info`
audio stream properties object:

- `length` — data type, units, precision
- `bitrate` — data type, units, whether it is CBR/VBR-average or something else
- `sample_rate` — data type, units
- `channels` — data type, values
- Any format-specific properties (e.g. `bits_per_sample` on FLAC and AIFF,
  `encoder_info` and `encoder_version` on MP3, `sketchy` on MP3)
- Whether any of these can be `None` or absent

### 7. Cover art / embedded artwork

Document how cover art is accessed for each format:
- ID3 `APIC` frames — how to retrieve, what `PictureType` values exist (enumerate all),
  what the `data` bytes are (raw image bytes)
- FLAC `.pictures` — how to retrieve, same fields as APIC
- MP4 cover art — how to retrieve from `covr` atom
- Whether mutagen validates or decodes the image data or returns raw bytes only
- What happens when there are multiple images in a file (e.g. front cover + back cover)

### 8. Reliability of tags in a real DJ library

This is critical for Crate — a DJ library is not a cleanly tagged collection.

Document what is known about tag quality and consistency for:
- **MP3 files purchased from Beatport** — which tags are reliably populated
- **MP3 files purchased from other download stores** (Juno, Traxsource, etc.) — any
  known differences in tagging practices
- **FLAC files purchased from Beatport or Bandcamp** — which tags are reliably populated
- **MP3 rips of vinyl** — what tags are typically present or absent; who writes them
- **AIFF files** — common in DJ libraries from Traktor users; tag reliability
- **WAV files** — ID3 support in WAV is inconsistently implemented; known issues
- **Files that have been through Traktor, Rekordbox, or Serato** — which standard tags
  get overwritten or modified by DJ software
- **BPM tag** (`TBPM`) reliability — is the value always present, always a round integer
  or decimal, always accurate?
- **Key tag** (`TKEY`) reliability — what notation is used (Open Key, Camelot, standard
  notation)? Is it consistently populated?
- **Genre tag** (`TCON`) in electronic music — free text or ID3 numeric codes? Reliable?

### 9. Encoding issues and edge cases

Document known issues that arise when reading real-world files:
- Files with no tags at all — what mutagen returns
- Files with corrupted tags — does mutagen raise an exception or return partial data?
- ID3v1 encoding issues — Latin-1 vs misidentified encodings
- ID3v2.3 frames stored with v2.4 encoding declarations — how mutagen handles this
- Files with both ID3v2 and APEv2 tags — which does mutagen prefer?
- Very large `APIC` frames (high-resolution artwork) — any memory or performance concerns
- Files with truncated or zero-length frames
- Non-standard TXXX description capitalisation — does `TXXX:bpm` differ from `TXXX:BPM`
  in mutagen's key access?
- What `mutagen.File()` returns for a file that is not audio (e.g. a PDF, a ZIP)

### 10. Field inventory

This section is the most important output for Crate's database design.

**Start from what mutagen actually exposes — not from what we want.**

Produce a complete inventory of every tag field and audio property that mutagen can return
from MP3, FLAC, AIFF, WAV, and M4A files. For each field:

- Field name / frame ID / tag key
- How to access it in mutagen (exact attribute or key path)
- Data type as returned by mutagen
- Which formats it applies to
- Whether it is always present, sometimes present, or rarely present in DJ files
- What it represents — be precise
- Any known reliability or quality issues for DJ library files

After completing the full inventory, note which fields map to these Crate candidates
as a secondary reference — but do not let this list constrain the inventory:
```
title, artist, album, label, catalogue_number, year, bpm, key, genre,
duration, bitrate, sample_rate, track_number, comment, isrc
```

If mutagen exposes fields not on this list that could be useful for a DJ library,
call them out explicitly. If a field on this list is unreliable or absent in practice,
say so directly.

### 11. The full tag read flow for a single file

Document the complete sequence of mutagen calls needed to extract a full set of
metadata from an audio file, as a step-by-step description (not code):

1. How to open the file and detect its format
2. How to check whether any tags are present
3. How to read each field — what call, where in the object, what the return value looks like
4. How to extract audio properties (bitrate, duration, sample rate)
5. How to extract cover art if present
6. How to handle missing fields — what to check, what to return when absent
7. How to handle format-specific differences (same field read differently from MP3 vs FLAC)

### 12. EasyID3 / EasyMP3 — the normalised interface

Document the EasyID3 interface fully:
- What problem it solves compared to raw ID3
- The complete key mapping — every key EasyID3 supports and what frame it maps to
- How to extend EasyID3 with custom keys (`EasyID3.RegisterTextKey`, etc.)
- Limitations of EasyID3 — what it cannot access that raw ID3 can
- Whether EasyID3 is recommended for a read-only import pipeline vs raw ID3

### 13. Installation

Document the correct installation procedure:
- `mutagen` — exact uv/pip install command and package name
- Python version compatibility — what versions are supported
- Any OS-level dependencies (there should be none, but confirm)
- A minimal Python script that opens one MP3, one FLAC, and one AIFF file and prints
  every tag key and value — to verify installation and understand what is actually in
  the files
- Any known installation issues on Windows or WSL2

---

## Output format

Write your findings as a single Markdown document saved to:

```
md/research/mutagen.md
```

Structure it as follows:

```
# mutagen and File Tags Research

## Sources
Links to every page consulted, so findings can be verified.

## What mutagen Is
Orientation: library scope, formats supported, maintenance status.

## Tag Format Landscape
ID3v1, ID3v2.3, ID3v2.4, Vorbis Comment, MP4 tags, RIFF INFO, APEv2.
Which format each file type uses. How mutagen normalises (or doesn't).

## mutagen Python API Reference
File(), FileType attributes, format-specific objects (MP3, FLAC, AIFF, WAV, MP4).
StreamInfo fields for each format.

## Standard ID3 Frame Reference
Every frame ID, human name, mutagen access pattern, data type.
Organised by category (text frames, URL frames, binary frames, etc.)

## DJ Software Custom Tags
Serato, Rekordbox, Traktor — what each writes, which frames, whether readable
without binary parsing. TXXX fields used across DJ software.

## Cover Art
How to access embedded artwork in each format. PictureType values.

## EasyID3 Reference
Complete key mapping. When to use vs raw ID3.

## Audio Properties Reference
Every .info field for MP3, FLAC, AIFF, WAV, M4A, OGG.

## Field Inventory
Complete table of every field and audio property mutagen exposes.
Format, access path, data type, always/sometimes/rarely present,
reliability in DJ library files.
Crate candidate fields cross-referenced at the end.

## Tag Reliability in DJ Libraries
What is confirmed about tag quality by format and purchase source.
BPM, key, and genre reliability specifically.

## Full Tag Read Flow
Step-by-step: open file → detect format → read fields → handle missing.
Format-specific differences documented.

## Encoding Issues and Edge Cases
Known issues with real-world files.

## Installation
Step-by-step for Python 3.11 and uv.

## Open Questions
Anything that cannot be confirmed from documentation alone and needs
a real test on actual DJ files in Phase 2.
```

---

## Definition of done

- [ ] `md/research/mutagen.md` exists and is written from primary sources
- [ ] All audio formats supported by mutagen are enumerated
- [ ] Every standard ID3 frame relevant to music metadata is documented with its
      frame ID, human name, mutagen access pattern, and data type
- [ ] DJ software custom tags (Serato, Rekordbox, Traktor) are documented — which
      frames each writes, and whether they are readable as plain strings
- [ ] Audio stream properties are documented for every relevant format (MP3, FLAC,
      AIFF, WAV, M4A)
- [ ] The field inventory covers every field mutagen can return, not just the Crate
      candidate list
- [ ] Cover art access is documented for each format including all PictureType values
- [ ] EasyID3 key mapping is enumerated completely
- [ ] Tag reliability in DJ libraries is documented separately from the field inventory
- [ ] The full tag read flow documents every step including all failure paths and
      format-specific differences
- [ ] Encoding issues and edge cases are documented
- [ ] Installation instructions are specific to Python 3.11 and uv
- [ ] All sources are linked so findings can be verified
- [ ] Open questions are listed so they can be answered by testing real files in Phase 2
