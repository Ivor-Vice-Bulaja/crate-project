# mutagen — File Tag Research

Tested: 2026-04-05  
Sample: 50 MP3 tracks from a techno/house DJ library (SEP2025 folder)  
Script: `scripts/test_importers.py --no-acoustid --no-discogs --no-cover-art`

---

## What mutagen returns

All fields are returned as strings (or None) except the boolean flags.
Audio stream properties come from `audio.info` and are always populated for a valid file.

### Audio stream properties (always present)

```
duration_seconds    float   — track length in seconds
bitrate_bps         int     — bitrate in bits per second
sample_rate_hz      int     — sample rate in Hz
channels            int     — channel count (1 = mono, 2 = stereo)
bits_per_sample     int     — bit depth; None for MP3 (not applicable)
```

MP3-only additions:
```
bitrate_mode        str     — "CBR", "VBR", "ABR", or "UNKNOWN"
encoder_info        str     — encoder string (e.g. "LAME 3.100"); often empty
is_sketchy          bool    — mutagen's internal flag for suspicious MP3 headers
```

### ID3 tag fields (MP3, AIFF, WAV)

```
tag_title           TIT2    str
tag_artist          TPE1    str
tag_album_artist    TPE2    str
tag_album           TALB    str
tag_label           TPUB    str
tag_genre           TCON    str
tag_isrc            TSRC    str
tag_copyright       TCOP    str
tag_track_number    TRCK    str    — may be "1/12" (track/total) format
tag_disc_number     TPOS    str
tag_bpm             TBPM    str    — raw string, not a float
tag_key             TKEY    str    — ID3v2.4 musical key (e.g. "Am")
tag_comment         COMM    str    — prefers empty-desc frame
tag_year_id3v24     TDRC    str    — ID3v2.4 recording time
tag_year_id3v23     TYER    str    — ID3v2.3 year (legacy)
tag_date_released   TDRL    str
tag_date_original   TDOR/TORY str
tag_catalogue_no    TXXX:CATALOGNUMBER or TXXX:CATALOGID  str
tag_initial_key_txxx TXXX:INITIALKEY  str  — DJ software extended key field
tag_energy          TXXX:ENERGY  str       — DJ software energy value
tag_id3_version     str     — e.g. "2.3.0" or "2.4.0"
```

### Boolean flags

```
has_embedded_art        bool    — True if APIC frame with PictureType.COVER_FRONT exists
has_serato_tags         bool    — True if any GEOB:Serato* frame present
has_traktor_tags        bool    — True if PRIV:TRAKTOR4 present
has_rekordbox_tags      bool    — True if any GEOB:*rekordbox* frame present
```

### Status fields

```
tags_present        bool    — False only for WAV without an ID3 chunk
tags_error          str     — None on success; error message on failure
tag_format_type     str     — "id3", "vorbiscomment", "mp4", or "none"
file_format         str     — "mp3", "flac", "aiff", "wav", "m4a", "ogg", "unknown"
```

---

## Field reliability — 50-track sample (all MP3)

| Field | Coverage | Notes |
|---|---|---|
| title | 100% | Always present |
| artist | 100% | Always present |
| album | 100% | Release title; always present |
| label | 100% | TPUB; always set by Beatport/download stores |
| genre | 100% | TCON; always set by stores |
| bpm | 100% | TBPM; always set |
| key | 100% | TKEY; always set |
| embedded cover art | 100% | APIC type 3; always present in store downloads |
| year (ID3v2.4 TDRC) | 50% | Set by some stores, absent in others |
| year (ID3v2.3 TYER) | 0% | Legacy field; not used by modern stores |
| catalogue number | 0% | Not written to TXXX by Beatport or similar |
| ISRC | 0% | Not present in DJ store downloads |
| Serato/Traktor/Rekordbox tags | 0% | These files have never been analysed in DJ software |
| initial key (TXXX) | not measured | Serato/Mixed In Key write this; absent here |
| energy (TXXX) | not measured | Mixed In Key writes this; absent here |

---

## Key findings

**What's reliable:** Title, artist, album, label, genre, BPM, key, and embedded art are all 100%
on Beatport-sourced store downloads. These fields can be trusted as the primary metadata source.

**What's missing:** Catalogue number is absent — Beatport does not write it to TXXX. This means
catno cannot be used as the primary Discogs search key directly from tags. It must come from
AcoustID/MusicBrainz lookup.

**Year is unreliable:** 50% coverage, no consistency between stores. Use MB year or Discogs year
as the authoritative source; tag year is a fallback of last resort.

**No ISRC:** Electronic music store downloads do not write ISRC to ID3 tags.

**BPM is a string:** `tag_bpm` from TBPM is a raw string (e.g. `"138"`, `"138.05"`). Cast to
float before use; handle values like `"0"` or empty strings that occasionally appear.

**Key encoding varies:** TKEY is intended for musical key per ID3v2.4. DJ software may also write
`TXXX:INITIALKEY` in a different format (e.g. `"10A"` Camelot vs `"Am"` standard). Both should
be read and stored separately; interpretation happens at the schema layer.

---

## Formats in a DJ library

Only MP3 observed in this sample. A real DJ library will also contain FLAC, AIFF, and WAV.
The importer handles all four via the same `read_tags()` public API — format detection is
automatic. M4A and OGG are supported but rare in DJ libraries.

---

## Error behaviour

`read_tags()` never raises. On any error it returns a dict with `tags_error` set and all
other fields as None. In 50 tracks, 0 errors were observed.
