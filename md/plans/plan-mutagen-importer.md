# Implementation Plan: mutagen Tag Reader Module

## Overview

`backend/importer/tags.py` opens a single audio file with mutagen and returns a flat
dictionary of raw tag values and audio stream properties. The module does not score,
rank, normalise, derive, or transform anything — it stores exactly what mutagen gives
us and lets later pipeline stages decide what to do with the values. The goal is to
lose as little information as possible from the file while never crashing on bad or
missing data. The module never calls `audio.save()` or writes to the file in any way.

---

## Function Interface

```python
def read_tags(path: str | Path) -> dict:
```

**Input**: a file path as `str` or `pathlib.Path`. Converted internally via
`os.fspath(path)` before passing to mutagen.

**Return**: a flat `dict` always. The function never raises an exception to the caller.
All error conditions are captured and returned as structured data in the dict.

**Error contract**:

| Condition | `tags_present` | `tags_error` | audio properties | tag fields |
|---|---|---|---|---|
| Success, tags present | `True` | `None` | populated | populated (None if absent) |
| Success, `audio.tags` is `None` | `False` | `None` | populated | all `None` |
| `mutagen.File()` returns `None` | `False` | `"unrecognised format"` | all `None` | all `None` |
| `mutagen.MutagenError` raised | `False` | `str(exception)` | `None` where unavailable | all `None` |
| Unexpected exception (top-level fallback) | `False` | `str(exception)` | all `None` | all `None` |

The function is the single public API of the module. No other functions are exported.

---

## Format Detection and Dispatch

**Detection method**: `mutagen.File(path)` detects format from file header bytes, not
from extension. No pre-filtering by extension is applied — mutagen's header detection
is sufficient and handles misnamed files.

**Decision: format-specific dispatch, not unified extraction.**

Rationale: ID3, VorbisComment, and MP4 have structurally different access patterns
(e.g., `audio.tags["TIT2"].text[0]` vs `audio.get("TITLE", [None])[0]` vs
`audio.get("©nam", [None])[0]`). Unifying them into one function would require
format-branching inside the function anyway. Format-specific helpers are more
readable, independently testable, and easier to extend.

**Format detection logic**:

```python
import mutagen
import mutagen.mp3
import mutagen.flac
import mutagen.aiff
import mutagen.wave
import mutagen.mp4
import mutagen.oggvorbis

audio = mutagen.File(path)

if audio is None:
    return _error_dict(path, "unknown", "unrecognised format")

if isinstance(audio, mutagen.mp3.MP3):
    file_format = "mp3"
    return _extract_id3(audio, path, file_format)

elif isinstance(audio, mutagen.flac.FLAC):
    file_format = "flac"
    return _extract_vorbis(audio, path, file_format)

elif isinstance(audio, mutagen.aiff.AIFF):
    file_format = "aiff"
    return _extract_id3(audio, path, file_format)

elif isinstance(audio, mutagen.wave.WAVE):
    file_format = "wav"
    return _extract_id3(audio, path, file_format)

elif isinstance(audio, mutagen.mp4.MP4):
    file_format = "m4a"
    return _extract_mp4(audio, path, file_format)

elif isinstance(audio, mutagen.oggvorbis.OggVorbis):
    file_format = "ogg"
    return _extract_vorbis(audio, path, file_format)

else:
    # Recognised by mutagen but not a target format (e.g. WMA, APE)
    file_format = "unknown"
    return _error_dict(path, file_format, "unsupported format")
```

**WAV special case**: `_extract_id3` handles WAV identically to MP3 and AIFF for the
tag layer. The key difference is that WAV's `.tags` may be `None` even for a valid,
playable file because mutagen does not read RIFF INFO chunks. `_extract_id3` detects
`audio.tags is None`, sets `tags_present = False` and `tags_error = None` (not an
error), and still populates audio properties from `audio.info`.

**OGG scope**: OGG Vorbis is in scope for Phase 2. The `_extract_vorbis` helper is
shared by both FLAC and OGG, with the difference that FLAC has `.pictures` and OGG
does not. The helper will check `hasattr(audio, "pictures")` for cover art.

**`mutagen.File()` returns `None`**: return immediately with `_error_dict(path,
"unknown", "unrecognised format")`. Log at WARNING.

---

## Tag Extraction — ID3 (MP3, AIFF, WAV)

Helper: `_extract_id3(audio, path, file_format) -> dict`

### Guard

```python
tags = audio.tags  # None for WAV without ID3 chunk; ID3 object otherwise
tags_present = tags is not None
```

If `tags is None`, skip all tag field access. Populate audio properties from
`audio.info` as normal. Set all tag fields to `None`.

### Frame Access Pattern

Every frame access uses a guard check, never bare key access:

```python
tag_title = tags["TIT2"].text[0] if tags and "TIT2" in tags else None
```

For `str()` coercion: use `.text[0]` rather than `str(frame)` to avoid the frame's
`__str__` representation including encoding information on some frame types.

### Field-by-Field Extraction

**Title**: `tags["TIT2"].text[0]` if `"TIT2" in tags` else `None`

**Artist**: `tags["TPE1"].text[0]` if `"TPE1" in tags` else `None`

**Album artist**: `tags["TPE2"].text[0]` if `"TPE2" in tags` else `None`

**Album**: `tags["TALB"].text[0]` if `"TALB" in tags` else `None`

**Label**: `tags["TPUB"].text[0]` if `"TPUB" in tags` else `None`

**Genre**: `tags["TCON"].text[0]` if `"TCON" in tags` else `None`. Stored raw —
`"(17)"` is stored as `"(17)"`, not translated to a genre name.

**Comment (COMM)**: call `tags.getall("COMM")` → list of COMM frame objects. Select
the first frame whose `.desc` is an empty string (`""`). If no such frame exists, use
the first frame overall. If the list is empty, store `None`. The language field is not
stored separately — only `.text[0]` from the selected frame.

**ISRC**: `tags["TSRC"].text[0]` if `"TSRC" in tags` else `None`

**Copyright**: `tags["TCOP"].text[0]` if `"TCOP" in tags` else `None`

**Track number**: `tags["TRCK"].text[0]` if `"TRCK" in tags` else `None`. Stored raw,
preserving `"3/12"` format.

**Disc number**: `tags["TPOS"].text[0]` if `"TPOS" in tags` else `None`. Stored raw,
preserving `"1/2"` format.

**BPM**: `tags["TBPM"].text[0]` if `"TBPM" in tags` else `None`. Stored as raw string
— `"128.00"` stays `"128.00"`.

**Key (TKEY)**: `tags["TKEY"].text[0]` if `"TKEY" in tags` else `None`. Stored raw,
notation not normalised.

### TYER vs TDRC Duality

Both fields are extracted independently and stored in separate output keys:

```python
tag_year_id3v24 = tags["TDRC"].text[0] if tags and "TDRC" in tags else None
tag_year_id3v23 = tags["TYER"].text[0] if tags and "TYER" in tags else None
tag_date_released = tags["TDRL"].text[0] if tags and "TDRL" in tags else None
tag_date_original = None
if tags:
    if "TDOR" in tags:
        tag_date_original = tags["TDOR"].text[0]
    elif "TORY" in tags:
        tag_date_original = tags["TORY"].text[0]
```

No truncation or parsing of date strings — all stored as mutagen returns them.

### TXXX Frame Access

TXXX frames are accessed by iterating `tags.getall("TXXX")` and checking `.desc`
case-insensitively. Direct key access (`tags["TXXX:CATALOGNUMBER"]`) requires exact
case matching, which is unreliable across taggers. The iterate-and-compare approach
handles both `"CATALOGNUMBER"` and `"catalognumber"`.

```python
def _get_txxx(tags, description: str) -> str | None:
    """Return the text of the first TXXX frame matching description (case-insensitive)."""
    for frame in tags.getall("TXXX"):
        if frame.desc.lower() == description.lower():
            return frame.text[0] if frame.text else None
    return None
```

**Catalogue number**: check `"CATALOGNUMBER"` first, fall back to `"CATALOGID"`:

```python
tag_catalogue_no = _get_txxx(tags, "CATALOGNUMBER") or _get_txxx(tags, "CATALOGID")
```

**Initial key (TXXX)**: stored separately from TKEY to preserve both values:

```python
tag_initial_key_txxx = _get_txxx(tags, "INITIALKEY")
```

**Energy**:

```python
tag_energy = _get_txxx(tags, "ENERGY")
```

### ID3 Version

```python
tag_id3_version = ".".join(str(v) for v in tags.version) if tags else None
# e.g. "2.3.0"
```

---

## Tag Extraction — VorbisComment (FLAC, OGG)

Helper: `_extract_vorbis(audio, path, file_format) -> dict`

VorbisComment tags are always present if the file has a tag block. `.tags` can still
be `None` for malformed files; guard accordingly.

### Field Access Pattern

```python
tags = audio.tags
tags_present = tags is not None
value = audio.get("TITLE", [None])[0]  # returns None if key absent
```

Note: `audio.get(key, [None])[0]` is used rather than `audio.tags.get(...)` to take
advantage of the case-insensitive lookup on the VorbisComment dict.

### Multi-value Fields

VorbisComment allows multiple values for the same key (e.g., two ARTIST fields for
a track with two artists). Decision: **join with `" / "`**. This preserves both
values in a single string, matching the common DJ library display convention, without
requiring the database schema to handle arrays. This applies to ARTIST, GENRE, and
any other field that could have multiple values.

```python
artists = audio.get("ARTIST", [])
tag_artist = " / ".join(artists) if artists else None
```

For fields unlikely to have multiple values (TITLE, ALBUM, etc.), use `[0]` directly
after confirming the list is non-empty.

### Field Mapping

| Output key | VorbisComment key(s) |
|---|---|
| `tag_title` | `TITLE` |
| `tag_artist` | `ARTIST` (join with `" / "` if multiple) |
| `tag_album_artist` | `ALBUMARTIST` |
| `tag_album` | `ALBUM` |
| `tag_label` | `ORGANIZATION` (primary), then `LABEL` as fallback |
| `tag_catalogue_no` | `CATALOGNUMBER` |
| `tag_genre` | `GENRE` (join with `" / "` if multiple) |
| `tag_comment` | `COMMENT` |
| `tag_isrc` | `ISRC` |
| `tag_copyright` | `COPYRIGHT` |
| `tag_track_number` | `TRACKNUMBER` |
| `tag_disc_number` | `DISCNUMBER` |
| `tag_bpm` | `BPM` |
| `tag_key` | `KEY` |
| `tag_initial_key_txxx` | `INITIALKEY` (treated as equivalent to TXXX:INITIALKEY in VorbisComment) |
| `tag_date_vorbis` | `DATE` |
| `tag_energy` | `ENERGY` |

For VorbisComment files:
- `tag_year_id3v24` = `None` (ID3-specific field)
- `tag_year_id3v23` = `None` (ID3-specific field)
- `tag_date_released` = `None` (ID3-specific field)
- `tag_date_original` = `None` (ID3-specific field)
- `tag_date_mp4` = `None` (MP4-specific field)
- `tag_id3_version` = `None`
- `tag_format_type` = `"vorbiscomment"`

### FLAC Cover Art

FLAC pictures are on `audio.pictures`, not in `.tags`. Check separately:

```python
has_embedded_art = False
if hasattr(audio, "pictures") and audio.pictures:
    has_embedded_art = any(p.type == 3 for p in audio.pictures)
```

Do not load picture bytes — `Picture` objects are already in memory when the FLAC is
opened, but the type check (`p.type`) does not require accessing `.data`.

For OGG Vorbis, `audio` has no `.pictures` attribute. `has_embedded_art` remains `False`.

---

## Tag Extraction — MP4 (M4A)

Helper: `_extract_mp4(audio, path, file_format) -> dict`

### Field Access Pattern

```python
value = audio.get("©nam", [None])[0]  # returns None if key absent
```

### Numeric Atom Handling

**trkn** returns `[(track_int, total_int)]` (a list containing one tuple):

```python
trkn = audio.get("trkn", [None])[0]
if trkn:
    tag_track_number = f"{trkn[0]}/{trkn[1]}" if trkn[1] else str(trkn[0])
else:
    tag_track_number = None
```

This stores the value as a string (e.g., `"3/12"` or `"3"`) for type consistency with
the ID3 and VorbisComment versions.

**disk** follows the same pattern:

```python
disk = audio.get("disk", [None])[0]
if disk:
    tag_disc_number = f"{disk[0]}/{disk[1]}" if disk[1] else str(disk[0])
else:
    tag_disc_number = None
```

**tmpo** returns `[int]`. Convert to string for type consistency across formats:

```python
tmpo = audio.get("tmpo", [None])[0]
tag_bpm = str(tmpo) if tmpo is not None else None
```

### Field Mapping

| Output key | MP4 atom key |
|---|---|
| `tag_title` | `©nam` |
| `tag_artist` | `©ART` |
| `tag_album_artist` | `aART` |
| `tag_album` | `©alb` |
| `tag_label` | `©pub` (if present); fallback to `----:com.apple.iTunes:LABEL` |
| `tag_catalogue_no` | `----:com.apple.iTunes:CATALOGNUMBER` (freeform atom) |
| `tag_genre` | `©gen` |
| `tag_comment` | `©cmt` |
| `tag_isrc` | `----:com.apple.iTunes:ISRC` |
| `tag_copyright` | `cprt` |
| `tag_track_number` | `trkn` (converted to string, see above) |
| `tag_disc_number` | `disk` (converted to string, see above) |
| `tag_bpm` | `tmpo` (converted to string, see above) |
| `tag_key` | `----:com.apple.iTunes:KEY` (freeform atom, if present) |
| `tag_date_mp4` | `©day` (raw — may be `"2019"` or `"2019-06-21"`) |

For freeform atoms (`----:...`), values are `MP4FreeForm` objects (subclass of bytes).
Decode via `.decode("utf-8", errors="replace")`:

```python
raw = audio.get("----:com.apple.iTunes:ISRC", [None])[0]
tag_isrc = raw.decode("utf-8", errors="replace") if raw else None
```

For MP4 files:
- `tag_year_id3v24` = `None`
- `tag_year_id3v23` = `None`
- `tag_date_released` = `None`
- `tag_date_original` = `None`
- `tag_date_vorbis` = `None`
- `tag_id3_version` = `None`
- `tag_format_type` = `"mp4"`
- `tag_initial_key_txxx` = `None` (no TXXX concept in MP4)
- `tag_energy` = `None` (unless a freeform atom is found — out of scope for Phase 2)

---

## Audio Properties Extraction

Audio properties come from `audio.info` and are always present for valid audio files.
They are populated regardless of whether `audio.tags` is `None`.

### Universal Fields (all formats)

```python
duration_seconds = audio.info.length          # float, seconds
bitrate_bps      = audio.info.bitrate         # int, bits per second
sample_rate_hz   = audio.info.sample_rate     # int, Hz
channels         = audio.info.channels        # int
```

### Format-Specific Fields

**bits_per_sample** — present on FLAC, AIFF, WAV, M4A; absent on MP3 and OGG:

```python
bits_per_sample = getattr(audio.info, "bits_per_sample", None)
```

**MP3-only** (MPEGInfo attributes):

```python
if file_format == "mp3":
    bitrate_mode = audio.info.bitrate_mode.name   # "CBR", "VBR", "ABR", or "UNKNOWN"
    encoder_info = audio.info.encoder_info or None  # empty string → None
    is_sketchy   = audio.info.sketchy              # bool
else:
    bitrate_mode = None
    encoder_info = None
    is_sketchy   = None
```

`audio.info.bitrate_mode` is a `BitrateMode` enum. Store its `.name` string, not the
integer value.

`encoder_info` is an empty string `""` when no LAME header is present; convert to
`None` for consistency.

### Format String

`file_format` is set during dispatch (see Format Detection section): `"mp3"`,
`"flac"`, `"aiff"`, `"wav"`, `"m4a"`, `"ogg"`, or `"unknown"`.

---

## Cover Art Detection

Store only a boolean `has_embedded_art`. Never store image bytes.

### ID3 (MP3, AIFF, WAV)

Do **not** call `tags.getall("APIC")` — this loads all APIC frame bytes into memory.
Instead, iterate over tag keys and check for the `"APIC:"` prefix:

```python
has_embedded_art = False
if tags:
    for key in tags.keys():
        if key.startswith("APIC:") or key == "APIC:":
            # Key is present; now check the type without loading bytes
            # Frame is already in memory (mutagen loads entire tag block)
            # but we avoid calling getall() which would re-parse
            frame = tags[key]
            if frame.type == 3:  # PictureType.COVER_FRONT
                has_embedded_art = True
                break
```

**Decision on APIC type**: `has_embedded_art` is `True` only when an APIC frame with
`type == 3` (COVER_FRONT) is found. An APIC frame with `type == 4` (back cover) or
`type == 0` (other) alone does not set `has_embedded_art = True`. Rationale: the
Cover Art Archive fetch step is concerned with whether a front cover is available
embedded in the file; non-front-cover images are not relevant to that decision.

**Memory note**: mutagen loads the entire tag block (including APIC bytes) into memory
when `mutagen.File()` is called. The bytes are already in memory once the file is
opened. The reason to avoid `getall("APIC")` is not to prevent loading (that has
already happened) but to avoid holding extra references to the decoded frame list.
Iterating `tags.keys()` and accessing individual frames avoids constructing the
`getall` list. See Memory Considerations section for the batch import context.

### FLAC

```python
has_embedded_art = False
if hasattr(audio, "pictures") and audio.pictures:
    has_embedded_art = any(p.type == 3 for p in audio.pictures)
```

### MP4

```python
covr = audio.get("covr", [])
has_embedded_art = len(covr) > 0
```

MP4 has no picture type concept equivalent to APIC type 3 — `covr` is always the
cover art atom. Any non-empty `covr` list means cover art is present.

---

## DJ Software Tag Detection

Detection only — no binary parsing. Three boolean flags:

**`has_serato_tags`**: True if any tag key starts with `"GEOB:Serato"`:

```python
has_serato_tags = False
if tags:
    has_serato_tags = any(k.startswith("GEOB:Serato") for k in tags.keys())
```

**`has_traktor_tags`**: True if `"PRIV:TRAKTOR4"` is in tag keys:

```python
has_traktor_tags = "PRIV:TRAKTOR4" in tags if tags else False
```

**`has_rekordbox_tags`**: best-effort. Rekordbox does not write GEOB frames (confirmed
in research — Rekordbox stores all analysis in its database). However, third-party
tools writing to files that are in a Rekordbox collection may add frames. Check for
any GEOB key containing `"rekordbox"` (case-insensitive):

```python
has_rekordbox_tags = False
if tags:
    has_rekordbox_tags = any(
        "rekordbox" in k.lower() for k in tags.keys() if k.startswith("GEOB:")
    )
```

This detection is acknowledged as speculative. The research doc does not confirm any
standard Rekordbox GEOB description string. Flag as an open question for Phase 2
validation against real Rekordbox files.

These flags apply to ID3-based formats only. For FLAC and M4A:
- `has_serato_tags` on FLAC: Serato writes to Vorbis Comment keys prefixed
  `SERATO_` — check for any key starting with `"SERATO_"` in the VorbisComment.
- `has_traktor_tags` on FLAC/M4A: `False` (Traktor uses PRIV frames in ID3 only).
- `has_rekordbox_tags` on FLAC/M4A: `False` for Phase 2.

---

## Output Schema

Full return dictionary. Every field is always present in the returned dict; value is
`None` when the data is absent or not applicable for the format.

| Key | Source | Python type | Nullable | Notes |
|---|---|---|---|---|
| **File identity** | | | | |
| `file_path` | `os.fspath(path)` | `str` | No | Always set |
| `file_format` | dispatch result | `str` | No | `"mp3"`, `"flac"`, `"aiff"`, `"wav"`, `"m4a"`, `"ogg"`, `"unknown"` |
| **Audio stream properties** | | | | |
| `duration_seconds` | `audio.info.length` | `float` | Yes | `None` on unrecognised format / MutagenError |
| `bitrate_bps` | `audio.info.bitrate` | `int` | Yes | `None` on unrecognised format / MutagenError |
| `bitrate_mode` | `audio.info.bitrate_mode.name` | `str` | Yes | MP3 only; `None` for all other formats |
| `sample_rate_hz` | `audio.info.sample_rate` | `int` | Yes | `None` on unrecognised format / MutagenError |
| `channels` | `audio.info.channels` | `int` | Yes | `None` on unrecognised format / MutagenError |
| `bits_per_sample` | `audio.info.bits_per_sample` | `int` | Yes | FLAC/AIFF/WAV/M4A only; `None` for MP3/OGG |
| `encoder_info` | `audio.info.encoder_info` | `str` | Yes | MP3 only; empty string converted to `None` |
| `is_sketchy` | `audio.info.sketchy` | `bool` | Yes | MP3 only; `None` for all other formats |
| **Core text fields** | | | | |
| `tag_title` | `TIT2` / `TITLE` / `©nam` | `str` | Yes | `None` if frame absent |
| `tag_artist` | `TPE1` / `ARTIST` / `©ART` | `str` | Yes | Multiple VorbisComment ARTIST joined with `" / "` |
| `tag_album_artist` | `TPE2` / `ALBUMARTIST` / `aART` | `str` | Yes | |
| `tag_album` | `TALB` / `ALBUM` / `©alb` | `str` | Yes | Often release title in DJ files |
| `tag_label` | `TPUB` / `ORGANIZATION` / `©pub` | `str` | Yes | |
| `tag_catalogue_no` | `TXXX:CATALOGNUMBER` or `TXXX:CATALOGID` / `CATALOGNUMBER` / freeform atom | `str` | Yes | |
| `tag_genre` | `TCON` / `GENRE` / `©gen` | `str` | Yes | Raw; `"(17)"` not translated |
| `tag_comment` | `COMM` / `COMMENT` / `©cmt` | `str` | Yes | First COMM with empty `.desc`; else first COMM overall |
| `tag_isrc` | `TSRC` / `ISRC` / freeform atom | `str` | Yes | |
| `tag_copyright` | `TCOP` / `COPYRIGHT` / `cprt` | `str` | Yes | |
| **Date / year** | | | | |
| `tag_year_id3v24` | `TDRC.text[0]` | `str` | Yes | ID3 only; `None` for FLAC/OGG/MP4 |
| `tag_year_id3v23` | `TYER.text[0]` | `str` | Yes | ID3 only; `None` for FLAC/OGG/MP4 |
| `tag_date_released` | `TDRL.text[0]` | `str` | Yes | ID3 v2.4 only |
| `tag_date_original` | `TDOR.text[0]` or `TORY.text[0]` | `str` | Yes | TDOR preferred (v2.4); fallback to TORY (v2.3) |
| `tag_date_vorbis` | `DATE` (VorbisComment) | `str` | Yes | FLAC/OGG only; `None` for ID3/MP4 |
| `tag_date_mp4` | `©day` | `str` | Yes | MP4 only; may be `"2019"` or `"2019-06-21"` |
| **Track / disc numbering** | | | | |
| `tag_track_number` | `TRCK` / `TRACKNUMBER` / `trkn` | `str` | Yes | Raw `"3/12"` preserved |
| `tag_disc_number` | `TPOS` / `DISCNUMBER` / `disk` | `str` | Yes | Raw `"1/2"` preserved |
| **DJ-relevant fields** | | | | |
| `tag_bpm` | `TBPM` / `BPM` / `tmpo` | `str` | Yes | Raw; `"128.00"` not converted; `tmpo` int converted to str |
| `tag_key` | `TKEY` / `KEY` | `str` | Yes | Raw; notation not normalised |
| `tag_energy` | `TXXX:ENERGY` / `ENERGY` | `str` | Yes | Plain text value from DJ tools (e.g. `"7"`) |
| `tag_initial_key_txxx` | `TXXX:INITIALKEY` / `INITIALKEY` (VorbisComment) | `str` | Yes | Stored separately from `tag_key` |
| **Cover art detection** | | | | |
| `has_embedded_art` | APIC type=3 / `.pictures` type=3 / `covr` | `bool` | No | Always `False` if no tags or unrecognised format |
| **DJ software detection** | | | | |
| `has_serato_tags` | `GEOB:Serato*` keys / `SERATO_*` VorbisComment keys | `bool` | No | Always `False` if no tags |
| `has_traktor_tags` | `PRIV:TRAKTOR4` key | `bool` | No | Always `False` if no tags or non-ID3 format |
| `has_rekordbox_tags` | `GEOB:*rekordbox*` keys (best-effort) | `bool` | No | Always `False` if no tags; detection unconfirmed |
| **Tag metadata** | | | | |
| `tag_id3_version` | `tags.version` tuple | `str` | Yes | e.g. `"2.3.0"`; `None` for non-ID3 formats |
| `tag_format_type` | derived from dispatch | `str` | No | `"id3"`, `"vorbiscomment"`, `"mp4"`, `"none"` |
| **Error / status** | | | | |
| `tags_error` | exception message or description | `str` | Yes | `None` on success (including `tags=None` case) |
| `tags_present` | `audio.tags is not None` | `bool` | No | Always set |

`tag_format_type` values:
- `"id3"` — MP3, AIFF, WAV (even when `audio.tags` is `None`)
- `"vorbiscomment"` — FLAC, OGG
- `"mp4"` — M4A
- `"none"` — unrecognised format or error

---

## Error Handling

The entire function body is wrapped in a top-level `try/except`. Each failure mode
returns a specific dict shape:

### `mutagen.File()` returns `None`

```
file_format     = "unknown"
tags_present    = False
tags_error      = "unrecognised format"
tag_format_type = "none"
duration_seconds, bitrate_bps, sample_rate_hz, channels = None
bits_per_sample, bitrate_mode, encoder_info, is_sketchy  = None
all tag_* fields = None
has_embedded_art, has_serato_tags, has_traktor_tags, has_rekordbox_tags = False
```

Log at WARNING.

### `mutagen.MutagenError` (corrupt file, IO error, truncated file)

```
tags_present = False
tags_error   = str(exception)
tag_format_type = "none"
audio properties = None (or populated if info was parsed before the error)
all tag_* fields = None
has_embedded_art, has_serato_tags, has_traktor_tags, has_rekordbox_tags = False
```

`mutagen.id3.ID3NoHeaderError` is a subclass of `MutagenError`. It is not raised by
`mutagen.File()` (which returns `None` or raises `MutagenError` for header issues).
The module does not call `ID3()` directly, so this is not expected. It is caught by
the `MutagenError` except clause regardless.

Log at WARNING.

### `audio.tags` is `None` (valid audio, no tag block — normal for WAV)

```
tags_present    = False
tags_error      = None    ← not an error
tag_format_type = appropriate format type ("id3" for WAV)
audio properties = populated from audio.info
all tag_* fields = None
has_embedded_art = False
has_serato_tags, has_traktor_tags, has_rekordbox_tags = False
```

Do not log — this is expected behaviour.

### Individual Frame Absent (KeyError on tag field access)

Use guard checks (`"TIT2" in tags`) rather than bare access. If a frame is absent,
that field is `None`. Individual missing frames do not affect other fields and are
not logged.

### Top-Level Fallback (unexpected exception)

```python
try:
    # entire function body
except mutagen.MutagenError as e:
    logger.warning("MutagenError reading %s: %s", path, e)
    return _error_dict(path, file_format_if_known, str(e))
except Exception as e:
    logger.error("Unexpected error reading tags from %s: %s", path, e, exc_info=True)
    return _error_dict(path, "unknown", str(e))
```

The top-level fallback ensures a dict is always returned. Any exception not caught
by the inner helpers propagates up to this level.

---

## Memory Considerations

### The APIC Loading Problem

mutagen loads the **entire ID3 tag block** into memory when `mutagen.File()` is called.
This includes all APIC frame bytes. For a batch import of 1,000 tracks where each
track has a 500 KB embedded cover, approximately 500 MB of image data will be held
in memory simultaneously if all file handles are open at once.

### Mitigation Strategy

**The pipeline processes one file at a time.** The import pipeline calls
`read_tags(path)`, receives the dict, and the `audio` object goes out of scope and
is garbage collected before the next file is opened. At no point are multiple file
handles open simultaneously. The 500 MB scenario does not apply to the sequential
single-file pipeline.

**Avoid `tags.getall("APIC")`**: even for a single file, calling `getall("APIC")`
constructs a list holding references to all APIC frame objects, keeping the image
bytes alive until the list is freed. Instead, iterate `tags.keys()` to find the
relevant frame keys, then access frames individually and check `.type` only.
This avoids constructing the full list and reduces peak memory within a single file
read.

**If concurrent processing is ever added**: ensure each worker processes one file at
a time and explicitly deletes the `audio` object (or uses a context manager if
mutagen ever adds one) before opening the next file.

---

## Configuration

**Decision: no configurable parameters in Phase 2. All extraction decisions are
hardcoded constants in the module.**

Rationale: the module has two decision points that might seem configurable — whether
to run TXXX extraction, and whether to check for DJ software tags. Both are
intentionally always-on because the performance cost is negligible (a single pass over
the in-memory frame list) and the data loss from skipping them is irreversible. Making
them configurable would add complexity with no benefit at this stage.

| Parameter | Decision | Location | Value |
|---|---|---|---|
| TXXX extraction | Always performed | Hardcoded | `True` |
| DJ software tag detection | Always performed | Hardcoded | `True` |
| Format acceptance | All mutagen-supported formats dispatched; non-target formats return `"unsupported format"` | Hardcoded | — |
| Log level for warnings | Uses standard `logging` module at WARNING / ERROR | Caller sets log level | — |

If future requirements call for skipping TXXX or DJ detection (e.g., performance
profiling shows it to be a bottleneck), introduce a parameter via `backend/config.py`
at that time.

---

## Test Plan

File: `backend/tests/test_importer/test_tags.py`

**No real audio files required.** All mutagen interactions are mocked via
`unittest.mock.patch("mutagen.File")`.

### Mock Fixture Strategy

Define minimal mock classes for each format's `.info` and `.tags` objects:

```python
from unittest.mock import MagicMock, patch

class MockMPEGInfo:
    length = 300.0
    bitrate = 320000
    sample_rate = 44100
    channels = 2
    bitrate_mode = MagicMock(name="CBR")
    encoder_info = "LAME3.100"
    sketchy = False
    # no bits_per_sample attribute

class MockFLACInfo:
    length = 300.0
    bitrate = 1411000
    sample_rate = 44100
    channels = 2
    bits_per_sample = 16

class MockWAVInfo:
    length = 300.0
    bitrate = 1411000
    sample_rate = 44100
    channels = 2
    bits_per_sample = 16

class MockMP4Info:
    length = 300.0
    bitrate = 256000
    sample_rate = 44100
    channels = 2
    bits_per_sample = 16
```

For ID3 tags, construct a `dict`-like mock with specific keys mapped to mock frame
objects:

```python
def make_id3_frame(text_value):
    frame = MagicMock()
    frame.text = [text_value]
    return frame

def make_txxx_frame(desc, text_value):
    frame = MagicMock()
    frame.desc = desc
    frame.text = [text_value]
    return frame
```

### Happy Path Tests

1. **MP3 with full ID3v2.4 tags** — mock `mutagen.File` returning a mock MP3 object
   with TDRC, TIT2, TPE1, TALB, TPUB, TCON, TBPM, TKEY, TSRC, TCOP, TRCK, TPOS,
   APIC (type=3), `GEOB:Serato Analysis`, `PRIV:TRAKTOR4` all present. Verify all
   output fields populated correctly.

2. **MP3 with ID3v2.3 TYER only** — TDRC absent, TYER present. Verify:
   `tag_year_id3v23 = "2019"`, `tag_year_id3v24 = None`.

3. **FLAC with VorbisComment** — mock returning a FLAC object with standard VorbisComment
   keys: TITLE, ARTIST, ALBUM, ORGANIZATION, DATE, BPM, KEY. Verify fields mapped to
   correct output keys. Verify `tag_date_vorbis` populated, `tag_year_id3v23` is `None`.

4. **M4A with MP4 atoms** — mock with `©nam`, `©ART`, `trkn = [(3, 12)]`,
   `tmpo = [128]`, `©day = "2019-06-21"`. Verify:
   - `tag_track_number = "3/12"`
   - `tag_bpm = "128"` (int converted to string)
   - `tag_date_mp4 = "2019-06-21"`

5. **AIFF** — mock returning AIFF object with ID3 tags. Verify `file_format = "aiff"`,
   `bits_per_sample` populated, tag fields extracted identically to MP3.

6. **WAV with ID3 chunk** — mock returning WAVE object with non-None ID3 tags. Verify
   tags read correctly, `tags_present = True`.

7. **WAV without ID3 chunk** — mock returning WAVE object with `audio.tags = None`.
   Verify: `tags_present = False`, `tags_error = None`, audio properties populated,
   all `tag_*` fields `None`.

### Edge Case Tests

8. **`mutagen.File()` returns `None`** — mock returns `None`. Verify:
   `tags_present = False`, `tags_error = "unrecognised format"`, `file_format = "unknown"`,
   no exception raised.

9. **`MutagenError` raised** — mock raises `mutagen.MutagenError("corrupt")`. Verify:
   `tags_present = False`, `tags_error = "corrupt"`, no exception raised.

10. **All tag fields absent** — mock MP3 with no frames (empty ID3 dict). Verify all
    `tag_*` fields are `None`, audio properties still populated.

11. **TBPM contains `"128.00"`** — verify `tag_bpm = "128.00"` (not converted to int).

12. **TCON contains `"(17)"`** — verify `tag_genre = "(17)"` (not translated).

13. **TRCK contains `"3/12"`** — verify `tag_track_number = "3/12"`.

14. **`TXXX:CATALOGNUMBER` present** — mock TXXX frame with `.desc = "CATALOGNUMBER"`.
    Verify `tag_catalogue_no` populated.

15. **`TXXX:CATALOGID` present (alternate casing)** — mock TXXX frame with
    `.desc = "CATALOGID"`. Verify `tag_catalogue_no` populated (falls back correctly).

16. **`TXXX:CATALOGNUMBER` and `TXXX:CATALOGID` both present** — verify
    `CATALOGNUMBER` value takes precedence.

17. **TKEY and `TXXX:INITIALKEY` both present** — verify both `tag_key` and
    `tag_initial_key_txxx` populated with their respective values (separate fields).

18. **APIC type=3 present** — mock frame with `.type = 3`. Verify `has_embedded_art = True`.

19. **APIC type=4 only** — mock frame with `.type = 4` (back cover), no type=3 frame.
    Verify `has_embedded_art = False`.

20. **`has_serato_tags` detection** — mock ID3 with key `"GEOB:Serato Analysis"` in
    `tags.keys()`. Verify `has_serato_tags = True`.

21. **`has_traktor_tags` detection** — mock ID3 with `"PRIV:TRAKTOR4"` in keys.
    Verify `has_traktor_tags = True`.

22. **COMM frame selection** — mock two COMM frames: one with `.desc = "Purchase URL"`
    and one with `.desc = ""`. Verify the empty-description frame is selected.

### MP3-Specific Tests

23. **`bitrate_mode` CBR** — mock `bitrate_mode.name = "CBR"`. Verify `bitrate_mode = "CBR"`.

24. **`sketchy = True`** — verify `is_sketchy = True`.

25. **`encoder_info` empty string** — verify stored as `None`.

26. **`encoder_info` non-empty** — verify stored as the string value.

### Top-Level Fallback Test

27. **Unexpected exception** — mock `mutagen.File` to raise a generic `ValueError`.
    Verify: a dict is returned, `tags_error` is set to the exception message, no
    exception propagated to caller.

---

## Open Questions

All 10 open questions from the research doc with interim decisions for this plan:

**OQ1 — Catalogue number field name in FLAC**
Uncertainty: is the VorbisComment key `CATALOGNUMBER`, `LABELNO`, or `LABEL_NUMBER`
in real electronic music files?
Decision: read `CATALOGNUMBER` as the primary key. `LABELNO` is unconfirmed — do not
read it in Phase 2. Flag for validation against actual Beatport and Juno FLAC downloads
before the database schema is finalised.

**OQ2 — Beatport TKEY notation in FLAC (Vorbis Comment key name)**
Uncertainty: does Beatport FLAC use `INITIALKEY` or `KEY` as the VorbisComment key name?
Decision: read both `INITIALKEY` (stored as `tag_initial_key_txxx`) and `KEY` (stored
as `tag_key`). This covers both conventions without guessing. Store raw; normalisation
of notation (Traditional vs Camelot vs Open Key) is deferred to a later pipeline stage.

**OQ3 — Serato TBPM vs GEOB BPM consistency**
Uncertainty: under what conditions does Serato write BPM to TBPM vs only to
`GEOB:Serato Autotags`?
Decision: read TBPM as the authoritative plain-text BPM source. The `has_serato_tags`
flag will tell the database that a Serato-analysed BPM may be in the binary GEOB.
Binary GEOB parsing (including Serato Autotags BPM) is deferred to Phase 2 validation.
Does not block the plan.

**OQ4 — Rekordbox TKEY notation (Traditional vs abbreviated)**
Uncertainty: does Rekordbox write `"A minor"` or `"Am"` to TKEY?
Decision: does not block implementation. Store raw value from TKEY. Normalisation
across notation systems is handled by a later pipeline stage. Flag for validation.

**OQ5 — TXXX:CATALOGNUMBER vs TXXX:CATALOGID**
Uncertainty: which TXXX description is more common in real DJ library files?
Decision: check both. Prefer `CATALOGNUMBER`; fall back to `CATALOGID`. The
case-insensitive TXXX iteration handles both regardless of tagger casing differences.
Flag for validation on real files in Phase 2.

**OQ6 — WAV files from Rekordbox USB export**
Finding confirmed in research doc: mutagen cannot read RIFF INFO chunks. WAV files
exported from Rekordbox to USB use RIFF INFO metadata and will have `audio.tags = None`.
Decision: return `tags_present = False`, `tags_error = None` for these files. This is
a known limitation documented in the module. Pipeline falls back to filename parsing.
If RIFF INFO support becomes necessary, implement a separate RIFF INFO parser using
Python `struct` outside mutagen. Does not block Phase 2.

**OQ7 — Serato GEOB binary format**
Does not affect the plan. Binary GEOB parsing is explicitly out of scope for Phase 2.
The `has_serato_tags` flag records presence for future reference.

**OQ8 — mutagen v2.3 save behaviour**
The research doc notes that `translate=True` (default) upgrades v2.3 frames to v2.4
in memory. A naive `audio.save()` call on a v2.3 file would re-save it as v2.4.
Decision: this module **never calls `audio.save()` or any write method**. The in-memory
upgrade does not affect tag field reads (TYER is still accessible as TYER). Not a
concern for this read-only module.

**OQ9 — Ogg Vorbis bitrate attributes**
Research confirms mutagen exposes only `audio.info.bitrate` (nominal bitrate). Lower
and upper bound bitrate fields from the Vorbis header are not exposed in the public API.
Decision: store `audio.info.bitrate` as `bitrate_bps`. No action needed.

**OQ10 — mutagen version currency**
v1.47.0 is documented (September 2023). Check PyPI for newer releases before
implementing the pipeline. If a newer version is available, review the changelog for
any breaking changes to the ID3, FLAC, AIFF, WAV, or MP4 APIs used in this plan.

---

## Implementation Order

Numbered steps for building `backend/importer/tags.py` in Phase 2:

1. **Install mutagen and confirm version**: `uv add mutagen`. Check `mutagen.__version__`
   against v1.47.0 and review changelog if newer.

2. **Write `_error_dict` helper**: implement the function that returns a fully-populated
   dict with all keys set to `None`/`False` and the specified `tags_error` value. This
   is the foundation for all error return paths.

3. **Write `_get_txxx` helper**: implement the case-insensitive TXXX frame lookup
   function. Write unit tests for this helper in isolation before using it in extractors.

4. **Write `_extract_audio_properties` helper**: reads `audio.info` attributes into
   a dict. Handles the format-specific fields (`bits_per_sample`, `bitrate_mode`, etc.)
   using `getattr` with `None` defaults. Write tests first using mock info objects.

5. **Write and test `_extract_id3`**: implement the ID3 extraction helper for MP3,
   AIFF, and WAV. Include TYER/TDRC dual extraction, TXXX iteration, cover art
   detection (keys iteration, not `getall`), and DJ software flag detection.
   Write tests for all edge cases (TCON raw, TRCK raw, APIC type checks) before
   moving on.

6. **Write and test `_extract_vorbis`**: implement the VorbisComment extraction helper
   for FLAC and OGG. Include multi-value join logic, FLAC `.pictures` cover art check,
   and Serato VorbisComment key detection.

7. **Write and test `_extract_mp4`**: implement the MP4 extraction helper. Include
   `trkn`/`disk` tuple-to-string conversion, `tmpo` int-to-string conversion, and
   freeform atom decoding.

8. **Write the top-level `read_tags` function**: implement format dispatch using
   `isinstance` checks. Wrap the entire body in `try/except` with `MutagenError`
   and `Exception` handlers. Wire all helpers together.

9. **Write integration-level tests for `read_tags`**: test happy paths for each format
   and all error paths (None return, MutagenError, tags=None, unexpected exception).
   These tests mock `mutagen.File` and verify the complete output dict structure.

10. **Run linting and formatting**: `uv run ruff check backend/importer/tags.py`
    and `uv run ruff format backend/importer/tags.py`.

11. **Manual spot-check (optional, Phase 2 validation)**: run `read_tags` against 10
    real files (2 MP3 from Beatport, 1 FLAC, 1 AIFF, 1 WAV, 1 M4A, 1 Serato-analysed
    file, 1 Traktor-analysed file, 1 file with no tags, 1 vinyl rip) and compare output
    to what Mp3tag shows. Confirm OQ1, OQ2, OQ4, OQ5 against real files.

12. **Update `CLAUDE.md` and `CURRENT_STATE.md`**: mark the mutagen research and
    importer plan as complete. Record any findings from step 11 that affect the
    database schema or open questions.
