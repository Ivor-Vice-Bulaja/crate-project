# mutagen and File Tags Research

Researched: 2026-04-05  
Sources: mutagen GitHub, PyPI, source code (_frames.py, flac.py, aiff.py, mp3/__init__.py, mp4/__init__.py, easyid3.py), Holzhaus/serato-tags documentation, ID3 specification references, Vorbis Comment spec, DJ software forum research.

---

## Sources

- https://github.com/quodlibet/mutagen (README, source files)
- https://pypi.org/project/mutagen/
- https://github.com/quodlibet/mutagen/blob/main/mutagen/id3/_frames.py
- https://github.com/quodlibet/mutagen/blob/main/mutagen/easyid3.py
- https://github.com/quodlibet/mutagen/blob/main/mutagen/flac.py
- https://github.com/quodlibet/mutagen/blob/main/mutagen/aiff.py
- https://github.com/quodlibet/mutagen/blob/main/mutagen/mp3/__init__.py
- https://github.com/quodlibet/mutagen/blob/main/mutagen/mp4/__init__.py
- https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md
- https://github.com/Holzhaus/serato-tags (README)
- https://wiki.xiph.org/VorbisComment
- https://xiph.org/vorbis/doc/v-comment.html
- https://id3.org/ID3v1
- https://community.mp3tag.de (various ID3 version discussions)
- https://community.pioneerdj.com (Rekordbox tag writing behaviour)
- https://forum.djtechtools.com (Traktor tag storage)
- https://community.native-instruments.com (Traktor4 custom tag)

---

## What mutagen Is

mutagen is a pure-Python library for reading and writing audio metadata. It handles the tag layer (metadata stored in the file) and the stream info layer (technical properties of the audio data, derived by parsing codec headers rather than tags). These two layers are always separate objects even when accessed through the same file handle.

**Supported formats and file extensions** (as of v1.47.0):

| Format | Typical extensions | Tag format mutagen uses |
|---|---|---|
| MP3 | .mp3 | ID3v1, ID3v2 (all versions) |
| FLAC | .flac | VorbisComment (via FLAC metadata blocks) |
| MP4 / AAC / ALAC | .m4a, .m4b, .m4p, .aac, .mp4 | iTunes/MP4 atoms |
| AIFF | .aif, .aiff, .aifc | ID3v2 (embedded in IFF chunk) |
| WAVE / WAV | .wav | ID3v2 (embedded in RIFF chunk) |
| Ogg Vorbis | .ogg | VorbisComment |
| Ogg FLAC | .oga | VorbisComment |
| Ogg Opus | .opus | OpusTags (VorbisComment variant) |
| Ogg Speex | .spx | VorbisComment |
| Ogg Theora | .ogv | VorbisComment |
| ASF / WMA | .wma, .asf, .wmv | ASF content description |
| Monkey's Audio | .ape | APEv2 |
| Musepack | .mpc | APEv2 |
| WavPack | .wv | APEv2 |
| OptimFROG | .ofr, .ofs | APEv2 |
| True Audio | .tta | ID3v2 or APEv2 |

**Formats not in mutagen** (relevant to DJs): no native support for stem files (.stem.mp4 is just MP4 and can be opened), no AAC-in-ADTS (.aac raw) tag support, no DSF, no DFF.

**Python version**: 3.10+ (CPython and PyPy). Works on Linux, Windows, macOS.

**Dependencies**: none beyond the Python standard library.

**Version**: 1.47.0 (September 2023). Actively maintained — 1,853+ commits, 63 releases. Licensed GPL v2 or later.

**Key design point**: mutagen's ID3 API is primarily targeted at ID3v2.4. By default, when it loads a v2.3 file and you call `save()`, it will write v2.4. Use `save(v2_version=3)` to keep v2.3. The `translate=True` default on `ID3()` means frames are automatically upgraded to v2.4 equivalents on load.

---

## Tag Format Landscape

### ID3v1

A fixed 128-byte block appended to the end of an MP3 file. Fields:

| Field | Size (bytes) | Encoding | Notes |
|---|---|---|---|
| Header | 3 | ASCII | Always "TAG" |
| Title | 30 | Latin-1 (ISO-8859-1) | Null-padded |
| Artist | 30 | Latin-1 | Null-padded |
| Album | 30 | Latin-1 | Null-padded |
| Year | 4 | Latin-1 | Numeric string |
| Comment | 30 (v1) or 28 (v1.1) | Latin-1 | |
| Track number | 1 | Binary integer | ID3v1.1 only; last 2 bytes of comment |
| Genre | 1 | Binary integer | Index into fixed list of 192 genres |

Limitations: 30-character field limit truncates long names. Latin-1 only — no UTF-8, no non-Western characters. Genre is a numeric index, not free text. No label, no key, no BPM. ID3v1.1 adds track number but no disc number. mutagen reads ID3v1 silently alongside ID3v2 when both are present; ID3v2 takes precedence.

### ID3v2.3 vs ID3v2.4

Both are in common use. ID3v2.3 (1999) is the older, more widely compatible version. ID3v2.4 (2000) adds features but has patchy support in older hardware players.

Key differences that matter for a DJ library:

| Aspect | ID3v2.3 | ID3v2.4 |
|---|---|---|
| Year/date | TYER (4-digit year only), TDAT (DDMM), TIME | TDRC (ISO 8601 full timestamp: YYYY, YYYY-MM, YYYY-MM-DD, etc.) |
| Original release | TORY (year only) | TDOR (full timestamp) |
| Encoding time | Not present | TDEN |
| Release time | Not present | TDRL |
| Tagging time | Not present | TDTG |
| String encoding | Latin-1, UTF-16 | Latin-1, UTF-16, UTF-16BE, UTF-8 |
| Multiple string values in one frame | Not supported | Supported (null-separated) |
| Unsynchronisation | Applies to whole tag | Applies per frame |
| Recommended save version | Most tools default to this | mutagen defaults to this |

**Which is more common in DJ libraries**: ID3v2.3 is more prevalent. Beatport historically wrote v2.3. Rekordbox uses v2.3 for existing tracks and v2.4 for newly added tracks (as of v6.8.4). Traktor reads both. Most hardware players (CDJs, Denon units) handle v2.3 reliably; v2.4 support is present but sometimes incomplete on older firmware.

**Coexistence**: A file can have both ID3v1 and ID3v2 simultaneously — ID3v2 is at the start of the file, ID3v1 is at the end. This is common. mutagen returns the ID3v2 tag when you access `.tags`; ID3v1 can be accessed explicitly.

**Mixed version frames**: Some files have an ID3v2.3 header but contain v2.4 frames (e.g., TDRC written into a v2.3 file). This is technically invalid. mutagen handles this pragmatically.

### Vorbis Comment

Used by FLAC and all Ogg container formats (Vorbis, Opus, Speex, Theora, FLAC-in-Ogg).

Structure: key=value pairs. Keys are ASCII strings, case-insensitive per spec. Values are UTF-8. Multiple values for the same key are allowed and encouraged (e.g., multiple ARTIST fields for a track with two artists). No binary data in Vorbis Comment fields — cover art uses a separate mechanism (METADATA_BLOCK_PICTURE for FLAC, embedded in the Ogg stream for others).

**Standard field names from the Vorbis spec** (none are mandatory):

```
TITLE           track title
ARTIST          artist/performer name (repeat for multiple artists)
ALBUM           album/release title
TRACKNUMBER     track number (integer as string)
DATE            release date (ISO 8601: YYYY, YYYY-MM, or YYYY-MM-DD)
COMMENT         freeform comment
GENRE           genre (freeform string)
ORGANIZATION    organisation (label)
DESCRIPTION     a description of the piece
CONTACT         contact information for the work
COPYRIGHT       copyright attribution
LICENSE         licence for the work
ISRC            ISRC code
LOCATION        location of recording
PERFORMER       performer name (distinct from ARTIST)
VERSION         version of the track (e.g., "Radio Edit")
```

**De facto standard fields** (widely supported beyond the minimal spec):

```
ALBUMARTIST       album-level artist (a.k.a. TPE2 equivalent)
DISCNUMBER        disc number within a set
TOTALTRACKS       total tracks on disc
TOTALDISCS        total discs in set
COMPOSER          composer name
CONDUCTOR         conductor
REMIXER           remixer name
LABEL             record label
CATALOGNUMBER     catalogue number
BPM               beats per minute (freeform string)
INITIALKEY        musical key
REPLAYGAIN_TRACK_GAIN   in dB, e.g. "-6.54 dB"
REPLAYGAIN_TRACK_PEAK   float 0.0–1.0
REPLAYGAIN_ALBUM_GAIN
REPLAYGAIN_ALBUM_PEAK
METADATA_BLOCK_PICTURE  base64-encoded FLAC Picture block (cover art)
ENCODER             encoder software name
ENCODED_BY          person who encoded
```

In mutagen, OGG/FLAC tags are accessed as a dict-like object where values are always lists of strings (even if only one value is present). Keys are stored and returned in whatever case the file uses, but lookups via mutagen are case-insensitive.

### MP4 / iTunes Atoms

MP4 metadata lives inside the moov → udta → meta → ilst atom hierarchy. Keys are four-byte codes. Most text fields use `©` (copyright symbol, 0xA9) as the first byte as a convention for iTunes-originated fields. Values are lists (to support multiple values).

Full list of standard atom keys mutagen handles — see the MP4 section of the API reference below.

Freeform atoms use the key prefix `----` (four hyphens). The full key is `----:mean:name` where `mean` is typically a reverse-domain string like `com.apple.iTunes` and `name` is the field name. Example: `----:com.apple.iTunes:iTunNORM`.

### RIFF INFO chunks for WAV

WAV files use RIFF chunks. The INFO LIST chunk can contain text metadata using four-character keys (INAM = name/title, IART = artist, etc.). **mutagen does not currently support RIFF INFO chunks**. When mutagen reads a WAV file, it looks for an `ID3 ` or `id3 ` subchunk within the RIFF structure and reads that as an ID3v2 tag. If no ID3 chunk is present, `.tags` is `None`. There is an open GitHub issue (#207) requesting RIFF INFO support that has been open for years — do not assume it will be added.

This means: WAV files tagged with RIFF INFO (e.g., by some mastering tools, Logic Pro, or Windows utilities) will have `tags = None` in mutagen even though they technically have metadata.

### APEv2

APEv2 is the native tag format for Monkey's Audio, Musepack, and WavPack. It sometimes appears on MP3 files written by old ripping software (e.g., foobar2000 in certain configurations). APEv2 tags in MP3 files can conflict with ID3 and cause problems with hardware decoders. When mutagen opens a file format that natively uses APEv2, it reads APEv2. For MP3 files that have both ID3 and APEv2, mutagen reads the ID3 tag (the MP3 class does not expose APEv2). APEv2 tags can be read from an MP3 directly with `mutagen.apev2.APEv2(filename)` if needed.

APEv2 is rare in a typical DJ library of downloaded electronic music. It appears mainly in files ripped with certain tools or downloaded from older sources.

---

## mutagen Python API Reference

### mutagen.File()

```
mutagen.File(fileobj, options=None, easy=False)
```

The universal entry point. Takes a filename (string or path-like) or a file object. Guesses the file type by reading the file header. Returns a `FileType` subclass instance, or `None` if the format cannot be determined.

**Return value possibilities**:
- `mutagen.mp3.MP3` (or `EasyMP3` if easy=True) for MP3
- `mutagen.flac.FLAC` for FLAC
- `mutagen.aiff.AIFF` for AIFF
- `mutagen.wave.WAVE` for WAV
- `mutagen.mp4.MP4` for M4A / MP4
- `mutagen.oggvorbis.OggVorbis` for Ogg Vorbis
- Other format-specific classes
- `None` if format is unrecognised (not audio, corrupt header, unknown extension)

**easy=True parameter**: Wraps ID3-based formats with the EasyID3 interface. Returns `EasyMP3` for MP3, uses `EasyID3` for tag access. For WAV files, `easy=True` does not correctly apply EasyID3 (known limitation, GitHub issue #632); the raw ID3 interface is used instead. FLAC files are always accessed via VorbisComment regardless of `easy=True`.

**Format detection**: Mutagen reads the file header bytes to identify format, not the file extension. Extension is used as a hint only. A file named `.mp3` with a FLAC header will be opened as FLAC.

**Failure cases**:
- Returns `None` for unrecognised formats (PDFs, ZIPs, images)
- Raises `mutagen.MutagenError` (or its subclasses) for file access errors
- Raises `mutagen.id3.ID3NoHeaderError` if an ID3-specific loader is used directly on a file without an ID3 header

### FileType Base Object

Every file returned by `mutagen.File()` inherits from `mutagen.FileType`. Key attributes and methods:

| Attribute/Method | Description |
|---|---|
| `.tags` | The tag object, or `None` if no tags present. Type varies by format. |
| `.info` | `StreamInfo` object with audio properties. Never `None` (always parsed). |
| `.filename` | Path string of the loaded file. |
| `.save()` | Write tags back to file. Format-specific keyword args available. |
| `.delete()` | Remove all tags from file. |
| `.add_tags()` | Add an empty tag container if none present. Raises error if tags already exist. |
| `.__getitem__(key)` | Tag access shortcut: `audio["TIT2"]` same as `audio.tags["TIT2"]`. |
| `.__setitem__(key, val)` | Tag assignment shortcut. |
| `.__delitem__(key)` | Tag deletion shortcut. |
| `.keys()` | List of tag keys present. |
| `.values()` | List of tag values. |
| `.items()` | Key-value pairs. |
| `.pprint()` | Human-readable string of all tags. |

### ID3 Tag Access (MP3, AIFF, WAV)

For ID3-based formats, `.tags` is a `mutagen.id3.ID3` object (or `mutagen.id3._tags.ID3Tags`). It behaves as a dict where:
- Keys are the frame's "HashKey": `"TIT2"` for simple frames, `"TXXX:description"` for TXXX, `"COMM:desc:lang"` for COMM, `"APIC:desc"` for APIC, `"GEOB:desc"` for GEOB, etc.
- Values are frame objects (e.g., `mutagen.id3.TIT2`, `mutagen.id3.TXXX`).

To get a frame: `audio.tags["TIT2"]` → TIT2 frame object  
To get the string value: `str(audio.tags["TIT2"])` or `audio.tags["TIT2"].text[0]`  
To get all frames of a type: `audio.tags.getall("TXXX")` → list of all TXXX frames

**Version attribute**: `audio.tags.version` returns a tuple like `(2, 3, 0)` for ID3v2.3. Available even after translate=True upgrades the frames.

**mutagen.id3.ID3 vs mutagen.mp3.MP3**: `ID3(filename)` opens only the tag layer, no audio properties. `MP3(filename)` opens both tag and audio properties (`.info`). Use `MP3` for all DJ library work.

### FLAC Tag Access

`.tags` is a `mutagen.flac.VComment` object, which is dict-like with case-insensitive key access. Values are always lists of strings: `audio["TITLE"]` → `["Track Title"]`. `.pictures` is a separate attribute (list of `mutagen.flac.Picture` objects), not part of `.tags`.

### MP4 Tag Access

`.tags` is a `mutagen.mp4.MP4Tags` object, dict-like. Keys are atom strings (`"©nam"`, `"©ART"`, etc.). Values are lists. Some atoms have typed wrappers — see cover art and numeric atom sections below.

### OggVorbis Tag Access

`.tags` is a `mutagen.oggvorbis.OggVCommentDict`, dict-like with string keys (case-insensitive on read) and list-of-strings values.

### WAVE Tag Access

`.tags` is `None` if no ID3 chunk found. If an ID3 chunk exists, `.tags` is an `ID3` object accessed identically to MP3 tags. RIFF INFO metadata is silently ignored by mutagen.

---

## Standard ID3 Frame Reference

All frames below are accessed as `audio.tags["FRAMEID"]` for single-descriptor frames, or `audio.tags["FRAMEID:desc"]` for frames with descriptors. Text frames return objects whose `.text` attribute is a list of strings; cast with `str()` for a joined string or index with `[0]` for the first value.

### Text Frames (T___)

| Frame ID | Name | Mutagen access | Data type | DJ library prevalence |
|---|---|---|---|---|
| TIT1 | Content group description | `audio["TIT1"].text[0]` | str | Rare |
| TIT2 | Title | `audio["TIT2"].text[0]` | str | Always present if any tags exist |
| TIT3 | Subtitle / description | `audio["TIT3"].text[0]` | str | Sometimes (remixes, versions) |
| TALB | Album | `audio["TALB"].text[0]` | str | Common |
| TPE1 | Lead artist | `audio["TPE1"].text[0]` | str | Always present if any tags exist |
| TPE2 | Band / orchestra / album artist | `audio["TPE2"].text[0]` | str | Common on store downloads |
| TPE3 | Conductor / interpreter | `audio["TPE3"].text[0]` | str | Rare |
| TPE4 | Interpreted / remixed by | `audio["TPE4"].text[0]` | str | Sometimes |
| TCOM | Composer | `audio["TCOM"].text[0]` | str | Sometimes |
| TEXT | Lyricist | `audio["TEXT"].text[0]` | str | Rare |
| TOLY | Original lyricist | `audio["TOLY"].text[0]` | str | Very rare |
| TPUB | Publisher / label | `audio["TPUB"].text[0]` | str | Sometimes on store downloads |
| TCON | Content type / genre | `audio["TCON"].text[0]` | str | Common but unreliable (see reliability section) |
| TRCK | Track number | `audio["TRCK"].text[0]` | str (e.g. "3" or "3/12") | Common |
| TPOS | Part of set / disc number | `audio["TPOS"].text[0]` | str (e.g. "1" or "1/2") | Sometimes |
| TYER | Year (v2.3 only) | `audio["TYER"].text[0]` | str (4-digit year) | Common in v2.3 files |
| TDAT | Date (v2.3 only) | `audio["TDAT"].text[0]` | str (DDMM) | Rarely populated |
| TDRC | Recording time (v2.4) | `audio["TDRC"].text[0]` | str (ISO 8601 timestamp) | Common in v2.4 files |
| TDRL | Release time (v2.4) | `audio["TDRL"].text[0]` | str (ISO 8601) | Rare |
| TDOR | Original release time (v2.4) | `audio["TDOR"].text[0]` | str (ISO 8601) | Rare |
| TORY | Original release year (v2.3) | `audio["TORY"].text[0]` | str (year) | Very rare |
| TBPM | Beats per minute | `audio["TBPM"].text[0]` | str (numeric) | Common from store downloads and DJ analysis |
| TKEY | Starting key | `audio["TKEY"].text[0]` | str | Sometimes (notation varies — see reliability) |
| TLEN | Length in milliseconds | `audio["TLEN"].text[0]` | str (integer ms) | Sometimes; may be wrong |
| TSRC | ISRC | `audio["TSRC"].text[0]` | str | Common on major-label releases; rare on electronic |
| TLAN | Language | `audio["TLAN"].text[0]` | str (ISO 639-2 code) | Very rare |
| TCOP | Copyright | `audio["TCOP"].text[0]` | str | Sometimes on store downloads |
| TENC | Encoded by | `audio["TENC"].text[0]` | str | Sometimes |
| TSSE | Encoder settings | `audio["TSSE"].text[0]` | str | Sometimes (LAME settings) |
| TFLT | File type | `audio["TFLT"].text[0]` | str | Very rare |
| TMED | Media type | `audio["TMED"].text[0]` | str | Very rare |
| TMOO | Mood | `audio["TMOO"].text[0]` | str | Rare |
| TSST | Set subtitle | `audio["TSST"].text[0]` | str | Very rare |
| TSOP | Performer sort order | `audio["TSOP"].text[0]` | str | Sometimes (iTunes files) |
| TSOA | Album sort order | `audio["TSOA"].text[0]` | str | Sometimes (iTunes files) |
| TSOT | Title sort order | `audio["TSOT"].text[0]` | str | Rare |
| TSO2 | Album artist sort (iTunes) | `audio["TSO2"].text[0]` | str | Sometimes (iTunes/Apple Music) |
| TSOC | Composer sort (iTunes) | `audio["TSOC"].text[0]` | str | Rare |
| TIPL | Involved people list (v2.4) | `audio["TIPL"].people` | list of [role, name] pairs | Rare |
| TMCL | Musicians credits list (v2.4) | `audio["TMCL"].people` | list of [role, name] pairs | Rare |
| TDTG | Tagging time (v2.4) | `audio["TDTG"].text[0]` | str | Rare |
| TDEN | Encoding time (v2.4) | `audio["TDEN"].text[0]` | str | Rare |
| TOWN | Owner / licensee | `audio["TOWN"].text[0]` | str | Very rare |
| TOFN | Original filename | `audio["TOFN"].text[0]` | str | Very rare |
| TDLY | Audio delay (ms) | `audio["TDLY"].text[0]` | str (integer) | Very rare |
| TOAL | Original album | `audio["TOAL"].text[0]` | str | Very rare |
| TOPE | Original artist | `audio["TOPE"].text[0]` | str | Very rare |
| TRSN | Radio station name | `audio["TRSN"].text[0]` | str | Very rare |
| TRSO | Radio station owner | `audio["TRSO"].text[0]` | str | Very rare |
| TOWN | Owner / licensee | `audio["TOWN"].text[0]` | str | Very rare |
| TCMP | iTunes compilation flag | `audio["TCMP"].text[0]` | str ("1" or "0") | iTunes files only |

**TXXX (user-defined text frame)**:
- Multiple TXXX frames can exist; distinguished by `.desc` attribute
- HashKey: `"TXXX:description"` — the description is the part after the colon
- Access: `audio.tags["TXXX:BeatportKey"]` (exact case match required — see edge cases)
- Attributes: `.encoding` (int), `.desc` (str), `.text` (list of str)
- Common TXXX descriptions in DJ files: `BPM`, `INITIALKEY`, `COMMENT`, `ENERGY`, `RATING`, `CATALOGNUMBER`, `ACOUSTID_ID`, `ACOUSTID_FINGERPRINT`, `MUSICBRAINZ_TRACKID`, `MUSICBRAINZ_ALBUMID`, `DISCOGS_RELEASE_ID`
- To iterate all TXXX: `audio.tags.getall("TXXX")` → list of TXXX frame objects

### Special Frames

**COMM (Comment)**:
- Multiple COMM frames allowed; distinguished by language + description
- HashKey: `"COMM:desc:lang"` (e.g., `"COMM::eng"` for no-description English comment)
- Attributes: `.encoding`, `.lang` (3-char ISO 639-2 code, e.g. "eng"), `.desc` (str), `.text` (list of str)
- Common usage: freeform comment, DJ notes, purchase URL
- Access all comments: `audio.tags.getall("COMM")`

**APIC (Attached Picture)**:
- Multiple APIC frames per file; distinguished by description
- HashKey: `"APIC:"` for no-description cover, `"APIC:desc"` otherwise
- Attributes: `.encoding`, `.mime` (str, e.g. "image/jpeg"), `.type` (int, PictureType), `.desc` (str), `.data` (bytes — raw image data)
- mutagen returns raw bytes; it does not decode the image
- PictureType enum values (ID3 standard, all 21 values):

| Value | Constant | Meaning |
|---|---|---|
| 0 | OTHER | Other |
| 1 | FILE_ICON | 32×32 PNG file icon |
| 2 | OTHER_FILE_ICON | Other file icon |
| 3 | COVER_FRONT | Front cover (use this for album art) |
| 4 | COVER_BACK | Back cover |
| 5 | LEAFLET_PAGE | Leaflet page |
| 6 | MEDIA | Media (e.g. CD label) |
| 7 | LEAD_ARTIST | Lead artist/soloist |
| 8 | ARTIST | Artist/performer |
| 9 | CONDUCTOR | Conductor |
| 10 | BAND | Band/orchestra |
| 11 | COMPOSER | Composer |
| 12 | LYRICIST | Lyricist/text writer |
| 13 | RECORDING_LOCATION | Recording location |
| 14 | DURING_RECORDING | During recording |
| 15 | DURING_PERFORMANCE | During performance |
| 16 | MOVIE_SCREEN_CAPTURE | Movie/video screen capture |
| 17 | COLOURED_FISH | A bright coloured fish |
| 18 | ILLUSTRATION | Illustration |
| 19 | BAND_LOGOTYPE | Band/artist logotype |
| 20 | PUBLISHER_LOGOTYPE | Publisher/Studio logotype |

**GEOB (General Encapsulated Object)**:
- Binary blob — NOT a picture
- Multiple allowed; distinguished by `.desc`
- HashKey: `"GEOB:description"` (e.g., `"GEOB:Serato Analysis"`)
- Attributes: `.encoding` (int), `.mime` (str, typically "application/octet-stream"), `.filename` (str), `.desc` (str), `.data` (bytes — binary payload)
- Data is always binary; plain-text reading without custom parsing is not possible
- This is the primary storage mechanism for Serato DJ metadata in MP3/AIFF files

**PRIV (Private Frame)**:
- HashKey: `"PRIV:owner_url"` where owner is a URL/identifier string
- Attributes: `.owner` (str), `.data` (bytes)
- Traktor uses a PRIV frame with owner `"TRAKTOR4"` to store cue points and beatgrid data

**TXXX (already documented above)**

**WXXX (User-defined URL)**:
- Attributes: `.encoding`, `.desc`, `.url` (str)
- HashKey: `"WXXX:description"`

**UFID (Unique File Identifier)**:
- HashKey: `"UFID:owner_url"`
- Attributes: `.owner` (str), `.data` (bytes)
- MusicBrainz writes `UFID:http://musicbrainz.org` with the recording UUID as ASCII bytes
- Access: `audio.tags["UFID:http://musicbrainz.org"].data.decode("ascii")`

**USLT (Unsynchronised lyrics)**:
- HashKey: `"USLT:desc:lang"`
- Attributes: `.encoding`, `.lang`, `.desc`, `.text` (str — full lyrics, not list)

**SYLT (Synchronised lyrics)**:
- HashKey: `"SYLT:desc:lang"`
- Attributes: `.encoding`, `.lang`, `.format` (timestamp format), `.type`, `.desc`, `.text` (list of (text, timestamp) tuples)

**PCNT (Play counter)**:
- HashKey: `"PCNT"`
- Attributes: `.count` (int)

**POPM (Popularimeter / rating)**:
- HashKey: `"POPM:email"`
- Attributes: `.email` (str), `.rating` (int, 0–255), `.count` (int, optional)
- Windows Media Player uses `POPM:Windows Media Player 9 Series` with rating scale: 0=unrated, 1=1star, 64=2stars, 128=3stars, 196=4stars, 255=5stars

**SEEK**:
- Attributes: `.offset` (int) — byte offset to next tag

**AENC (Audio encryption)**:
- Attributes: `.owner` (str), `.preview_start` (int), `.preview_length` (int), `.data` (bytes)

**CHAP (Chapter)**:
- Attributes: `.element_id` (str), `.start_time` (int, ms), `.end_time` (int, ms), `.start_offset` (int), `.end_offset` (int), `.sub_frames` (dict of sub-frames)

**CTOC (Table of contents)**:
- Attributes: `.element_id` (str), `.flags` (int), `.child_element_ids` (list of str), `.sub_frames` (dict)

**RVA2 (Relative volume adjustment v2)**:
- Attributes: `.desc` (str), `.channel` (int), `.gain` (float, dB), `.peak` (float)
- Used for ReplayGain data in some taggers

### URL Frames (W___)

| Frame ID | Name |
|---|---|
| WCOM | Commercial information URL |
| WCOP | Copyright information URL |
| WOAF | Official audio file webpage |
| WOAR | Official artist/performer webpage |
| WOAS | Official audio source webpage |
| WORS | Official radio station homepage |
| WPAY | Payment URL |
| WPUB | Publisher's official webpage |

All URL frames: HashKey is `"WFOO"` (no descriptor), attribute is `.url` (str). WXXX has a descriptor.

---

## DJ Software Custom Tags

### Serato DJ

Serato stores all analysis data in binary format. No Serato data is plain-text readable without custom parsing.

**In MP3 and AIFF files** (ID3v2 GEOB frames):

| GEOB description | Content | Binary? |
|---|---|---|
| `Serato Analysis` | Serato version information | Yes — binary |
| `Serato Autotags` | BPM and gain values | Yes — binary (BPM is here, not in TBPM) |
| `Serato BeatGrid` | Beatgrid markers (mostly documented) | Yes — binary |
| `Serato Markers_` | Hot cues, saved loops (legacy format) | Yes — binary |
| `Serato Markers2` | Hot cues, saved loops (current format) | Yes — binary |
| `Serato Overview` | Waveform overview data | Yes — binary |
| `Serato Offsets_` | (MP3 only, not yet documented) | Yes — binary |

Access in mutagen: `audio.tags["GEOB:Serato Autotags"].data` → raw bytes  
To read BPM from Serato data requires decoding the binary format (documented in github.com/Holzhaus/serato-tags). The standard TBPM frame may or may not be present or accurate depending on Serato version and user settings — do not rely on TBPM alone if Serato analysis is present.

**In FLAC files** (Vorbis Comment keys, data base64-encoded):

| Key | Content |
|---|---|
| `SERATO_ANALYSIS` | Analysis version |
| `SERATO_AUTOGAIN` | Gain value |
| `SERATO_BEATGRID` | Beatgrid markers |
| `SERATO_MARKERS_V2` | Hot cues, saved loops |
| `SERATO_OVERVIEW` | Waveform overview |
| `SERATO_RELVOL` | Relative volume |
| `SERATO_VIDEO_ASSOC` | Video association |

Format: base64-encoded (no padding, linefeeds every 72 chars). Decoded data: null-terminated `application/octet-stream`, null byte, null-terminated field name, then binary payload. Not plain-text readable.

**In MP4/M4A files** (freeform atoms under `com.serato.dj`): `analysisVersion`, `autgain`, `beatgrid`, `markers`, `markersv2`, `overview`, `relvol`, `videoassociation`. Also base64-encoded binary.

**In Ogg Vorbis**: `serato_analysis_ver`, `serato_overview`, `serato_beatgrid`, `serato_markers`, `serato_markers2`. Different binary format from other file types.

**Standard tags that Serato reads from FLAC**: ARTIST, TITLE, ALBUM, GENRE, DATE, BPM, INITIALKEY, COMMENT, TRACKNUMBER. Serato has known issues reading REMIXER, LABEL fields from FLAC Vorbis Comments.

**Serato and standard TBPM**: Serato may write BPM to the TBPM frame in addition to `Serato Autotags`, depending on version and settings. Not guaranteed. Always check both.

### Rekordbox (Pioneer)

Rekordbox's primary approach is database-first. Analysis data (BPM, key, beat grid, cue points, waveform, hot cues, memory cues, ratings) is stored in Rekordbox's internal SQLite database, not in file tags by default.

**What Rekordbox does write to files**:
- Standard ID3 tags it reads on import (title, artist, album, etc.) are preserved unchanged
- **Key** (musical key as standard notation): written to `TKEY` frame only if the user explicitly enables "Write value to the ID3 tag" in Settings → Analysis → Key Analysis. Not written by default.
- No GEOB frames
- No TXXX frames for analysis data
- RIFF INFO for WAV files; Vorbis Comment for FLAC

**Rekordbox ID3 version**: Uses v2.3 for files that already have v2.3 tags; uses v2.4 for newly-added tracks (as of v6.8.4).

**What is NOT written to files by Rekordbox**: beat grid, cue points, memory cues, waveform data, energy level, play count, hot cue colours. All of these remain in the database only.

**Third-party tools (e.g., Mixed In Key)** write to Rekordbox-associated tracks using standard TXXX frames like `TXXX:INITIALKEY`, `TXXX:COMMENT`, `TXXX:ENERGY`.

### Traktor (Native Instruments)

Traktor uses a proprietary PRIV frame:

| Frame | Content |
|---|---|
| `PRIV:TRAKTOR4` | BPM, cue points, beat grid, loop data — binary format |

The option to write analysis data to files must be enabled in Traktor preferences. When enabled, cue points and beatgrid are embedded in the PRIV frame. When disabled (the default in some versions), all data remains in Traktor's `collection.nml` XML database file.

**What Traktor reads/writes for standard fields**: reads and preserves standard ID3 text frames. Does not write analysis data to TBPM or TKEY by default.

**Important**: Editing ID3 tags externally (e.g., with Mp3tag) may cause Traktor to reset or lose cue points and colors for that track.

### VirtualDJ

VirtualDJ primarily uses its own XML database for analysis data. It reads standard ID3 tags and writes basic tag fields (title, artist, year, BPM, comment) to files when explicitly triggered. It does not use TXXX custom frames. Most of its metadata (rating, color, grouping, cue points, video layer) remains in the VirtualDJ XML database.

### Common TXXX Fields Across DJ Software

| TXXX description | Who writes it | Readable as string? |
|---|---|---|
| `INITIALKEY` | Mixed In Key, One Tagger, some taggers | Yes — plain string (e.g. "8A", "12d", "Am") |
| `BPM` | Some DJ software; alternative to TBPM | Yes — numeric string |
| `ENERGY` | Mixed In Key (1–10 scale) | Yes — "7" |
| `COMMENT` | Mixed In Key, various | Yes — plain string |
| `CATALOGNUMBER` | Mp3tag, beets, One Tagger | Yes — plain string |
| `ACOUSTID_ID` | beets, EasyID3 | Yes — UUID string |
| `ACOUSTID_FINGERPRINT` | beets | Yes — base64 string (long) |
| `MUSICBRAINZ_TRACKID` | beets, picard | Yes — UUID string |
| `MUSICBRAINZ_ALBUMID` | beets, picard | Yes — UUID string |
| `MUSICBRAINZ_ALBUMARTISTID` | beets, picard | Yes — UUID string |
| `DISCOGS_RELEASE_ID` | One Tagger, beets | Yes — integer string |

**Summary: what is plain-text readable vs requires binary parsing**:
- Plain-text readable: all T___ text frames, all TXXX frames, COMM, USLT, all W___ URL frames
- Requires binary parsing: GEOB (all Serato and Rekordbox partner data), PRIV:TRAKTOR4, APIC (image data), MCDI, ETCO, SYLT, AENC
- The raw bytes are always accessible via mutagen (`.data` attribute); parsing is the developer's responsibility

---

## Cover Art

### ID3 APIC (MP3, AIFF, WAV)

Access: `audio.tags.getall("APIC")` → list of APIC frame objects  
Single front cover (most common): `audio.tags["APIC:"]` (empty description)

Each APIC frame object has:
- `.mime` (str): MIME type, typically "image/jpeg" or "image/png"
- `.type` (int): PictureType value (3 = COVER_FRONT is the standard for album art)
- `.desc` (str): description, usually empty string for front cover
- `.data` (bytes): raw image bytes — mutagen does NOT decode the image
- `.encoding` (int): text encoding for the description field (irrelevant for the image data)

Multiple images in one file: allowed and common (e.g., front cover type 3 + back cover type 4). Each must have a unique description string (two APIC frames of the same type with the same description are technically invalid but mutagen reads the first one).

Memory note: A high-resolution JPEG front cover is typically 300–500 KB. Loading a large library of files into memory simultaneously will load all cover art bytes. For an import pipeline reading tags without needing images, skip APIC by filtering it out after load.

### FLAC Pictures

FLAC stores pictures in separate metadata blocks, not in the VorbisComment.

Access: `audio.pictures` → list of `mutagen.flac.Picture` objects  
(Note: this is `audio.pictures`, not `audio.tags["something"]`)

Each Picture object fields:
- `.type` (int): same PictureType enum values as APIC (0–20)
- `.mime` (str): MIME type
- `.desc` (str): description
- `.width` (int): width in pixels (0 if unknown)
- `.height` (int): height in pixels (0 if unknown)
- `.depth` (int): colour depth in bits-per-pixel (0 if unknown)
- `.colors` (int): number of colours for indexed formats like GIF; 0 for non-indexed
- `.data` (bytes): raw image bytes

### MP4 Cover Art

Access: `audio.tags["covr"]` → list of `mutagen.mp4.MP4Cover` objects  
`MP4Cover` is a subclass of `bytes` (so it IS the image data) with an additional `.imageformat` attribute:
- `mutagen.mp4.MP4Cover.FORMAT_JPEG` = 13
- `mutagen.mp4.MP4Cover.FORMAT_PNG` = 14

### Ogg Vorbis / Ogg Opus Cover Art

Stored in a `METADATA_BLOCK_PICTURE` Vorbis Comment field as a base64-encoded FLAC Picture block. Access via the VorbisComment dict: `audio["metadata_block_picture"]` → list of base64 strings. Decode with `base64.b64decode()` then parse as a FLAC Picture block. This is awkward; many applications handle it transparently.

---

## EasyID3 Reference

### What Problem It Solves

Raw ID3 access requires knowing frame IDs (`TIT2`, `TPE1`, etc.) and working with frame objects. EasyID3 wraps this in a dict-like interface with human-readable keys (`title`, `artist`) and string values, making it behave more like VorbisComment or APEv2.

### Complete Key Mapping

| EasyID3 key | ID3 Frame | Notes |
|---|---|---|
| `title` | TIT2 | |
| `artist` | TPE1 | |
| `albumartist` | TPE2 | |
| `album` | TALB | |
| `date` | TDRC | |
| `originaldate` | TDOR | |
| `tracknumber` | TRCK | Returns string like "3" or "3/12" |
| `discnumber` | TPOS | |
| `composer` | TCOM | |
| `conductor` | TPE3 | |
| `arranger` | TPE4 | |
| `lyricist` | TEXT (author) | |
| `author` | TOLY | |
| `version` | TIT3 | |
| `grouping` | TIT1 | |
| `discsubtitle` | TSST | |
| `language` | TLAN | |
| `genre` | TCON | |
| `bpm` | TBPM | |
| `mood` | TMOO | |
| `copyright` | TCOP | |
| `encodedby` | TENC | |
| `organization` | TPUB | |
| `length` | TLEN | |
| `media` | TMED | |
| `isrc` | TSRC | |
| `compilation` | TCMP | |
| `albumsort` | TSOA | |
| `albumartistsort` | TSO2 | |
| `artistsort` | TSOP | |
| `titlesort` | TSOT | |
| `composersort` | TSOC | |
| `website` | WOAR | Returns list |
| `replaygain_track_gain` | RVA2 | |
| `replaygain_track_peak` | RVA2 | |
| `replaygain_album_gain` | RVA2 | |
| `replaygain_album_peak` | RVA2 | |
| `musicbrainz_trackid` | UFID:http://musicbrainz.org | |
| `musicbrainz_artistid` | TXXX:musicbrainz_artistid | |
| `musicbrainz_albumid` | TXXX:musicbrainz_albumid | |
| `musicbrainz_albumartistid` | TXXX:musicbrainz_albumartistid | |
| `musicbrainz_trmid` | TXXX:musicbrainz_trmid | |
| `musicbrainz_discid` | TXXX:musicbrainz_discid | |
| `musicbrainz_albumstatus` | TXXX:musicbrainz_albumstatus | |
| `musicbrainz_albumtype` | TXXX:musicbrainz_albumtype | |
| `musicbrainz_releasetrackid` | TXXX:musicbrainz_releasetrackid | |
| `musicbrainz_releasegroupid` | TXXX:musicbrainz_releasegroupid | |
| `musicbrainz_workid` | TXXX:musicbrainz_workid | |
| `releasecountry` | TXXX:releasecountry | |
| `asin` | TXXX:asin | |
| `barcode` | TXXX:barcode | |
| `catalognumber` | TXXX:catalognumber | |
| `acoustid_fingerprint` | TXXX:acoustid_fingerprint | |
| `acoustid_id` | TXXX:acoustid_id | |

### Extending EasyID3

```
EasyID3.RegisterTextKey("label", "TPUB")          # map key to text frame
EasyID3.RegisterTXXXKey("initialkey", "INITIALKEY")  # map to TXXX:INITIALKEY
EasyID3.RegisterKey("key", getter, setter, deleter)   # full custom handler
```

### Limitations of EasyID3

- Cannot access APIC (cover art) — no getter for binary frames
- Cannot access GEOB (DJ software data)
- Cannot access COMM (comments) — no key registered by default
- Cannot access USLT (lyrics)
- Cannot access POPM, PCNT
- Values are always lists of strings (even single values); use `[0]` to get the string
- Only accesses one frame per key even if multiple frames of the same type exist

### Recommendation for a Read-Only Import Pipeline

Use **raw ID3** (`mutagen.mp3.MP3(filename)` or `mutagen.File(filename)`), not EasyID3. Reasons:
- EasyID3 hides frame-level data needed for GEOB, APIC, COMM, TXXX with custom descriptions
- For the Crate import pipeline, you need TBPM, TKEY, TPUB, TSRC, and custom TXXX fields that EasyID3 does not map
- Raw ID3 access is not significantly more complex for reading; EasyID3's simplification is primarily for writing
- EasyID3's WAV support is broken (does not apply to WAV files via `mutagen.File(easy=True)`)

---

## Audio Properties Reference

All audio properties are on `audio.info` (a `StreamInfo` subclass). These are derived from the audio data, not from tags — they exist even if no tags are present.

### MP3 (mutagen.mp3.MPEGInfo)

| Attribute | Type | Description | Can be None? |
|---|---|---|---|
| `length` | float | Duration in seconds | No |
| `bitrate` | int | Bitrate in bits per second. For VBR, estimated from first frame or Xing header | No |
| `bitrate_mode` | BitrateMode | `CBR`, `VBR`, `ABR`, or `UNKNOWN` | No |
| `sample_rate` | int | Sample rate in Hz (typically 44100 or 48000) | No |
| `channels` | int | Number of channels (1 or 2) | No |
| `version` | float | MPEG version: 1.0, 2.0, or 2.5 | No |
| `layer` | int | MPEG layer: 1, 2, or 3 | No |
| `mode` | int | Channel mode: 0=Stereo, 1=Joint stereo, 2=Dual channel, 3=Mono | No |
| `encoder_info` | str | Encoder info string (starts with "LAME" if LAME tag present, else empty string) | No |
| `encoder_settings` | str | Guessed encoding settings from LAME tag | No |
| `sketchy` | bool | True if file may not be valid MPEG audio | No |
| `track_gain` | float or None | ReplayGain track gain in dB (from LAME/RG header) | Yes |
| `track_peak` | float or None | ReplayGain track peak | Yes |
| `album_gain` | float or None | ReplayGain album gain in dB | Yes |

Note: `bits_per_sample` does not exist on MPEGInfo — MP3 is a lossy format without a meaningful sample depth.

### FLAC (mutagen.flac.StreamInfo)

| Attribute | Type | Description | Can be None? |
|---|---|---|---|
| `length` | float | Duration in seconds | No |
| `bitrate` | int | Bitrate in bits per second | No |
| `sample_rate` | int | Sample rate in Hz | No |
| `channels` | int | Number of channels | No |
| `bits_per_sample` | int | Bits per sample (typically 16 or 24) | No |
| `total_samples` | int | Total PCM samples in file | No |
| `min_blocksize` | int | Minimum audio block size | No |
| `max_blocksize` | int | Maximum audio block size | No |
| `min_framesize` | int | Minimum frame size in bytes | No |
| `max_framesize` | int | Maximum frame size in bytes | No |
| `md5_signature` | int | MD5 hash of unencoded audio data (stored as integer) | No |

Note: changes to FLAC `StreamInfo` attributes are rewritten to the file on `save()`.

### AIFF (mutagen.aiff.AIFFInfo)

| Attribute | Type | Description | Can be None? |
|---|---|---|---|
| `length` | float | Duration in seconds | No |
| `bitrate` | int | Bitrate in bits per second | No |
| `sample_rate` | int | Sample rate in Hz | No |
| `channels` | int | Number of channels | No |
| `bits_per_sample` | int | Bits per sample (also aliased as `sample_size`) | No |

Parsed from the COMM chunk. Raises `OverflowError` for invalid sample rates.

### WAV (mutagen.wave.WaveInfo)

| Attribute | Type | Description | Can be None? |
|---|---|---|---|
| `length` | float | Duration in seconds | No |
| `bitrate` | int | Bitrate in bits per second | No |
| `sample_rate` | int | Sample rate in Hz | No |
| `channels` | int | Number of channels | No |
| `bits_per_sample` | int | Bits per sample | No |

Parsed from the `fmt` and `data` chunks.

### M4A / MP4 (mutagen.mp4.MP4Info)

| Attribute | Type | Description | Can be None? |
|---|---|---|---|
| `length` | float | Duration in seconds | No |
| `bitrate` | int | Bitrate in bits per second | No |
| `sample_rate` | int | Sample rate in Hz | No |
| `channels` | int | Number of channels | No |
| `bits_per_sample` | int | Bits per sample | No |
| `codec` | str | Codec identifier, e.g. "mp4a.40.2" (AAC-LC), "alac" | No |
| `codec_description` | str | Human-readable codec name, e.g. "AAC LC" | No |

### Ogg Vorbis (mutagen.oggvorbis.OggVorbisInfo)

| Attribute | Type | Description | Can be None? |
|---|---|---|---|
| `length` | float | Duration in seconds | No |
| `bitrate` | int | Nominal bitrate in bits per second | No |
| `sample_rate` | int | Sample rate in Hz | No |
| `channels` | int | Number of channels | No |

Note: Ogg Vorbis headers contain three bitrate fields (nominal, lower bound, upper bound). mutagen exposes only the nominal bitrate as `bitrate`.

---

## MP4 Atom Key Reference

Full list of MP4 atom keys mutagen handles natively:

**Text atoms** (values are lists of strings):
```
©nam    title
©alb    album
©ART    artist
aART    album artist
©wrt    composer
©day    year / date
©cmt    comment
©gen    genre (freeform)
©lyr    lyrics
©too    encoded by / encoder
cprt    copyright
desc    description / subtitle
soal    album sort order
soaa    album artist sort order
soar    artist sort order
sonm    title sort order
soco    composer sort order
sosn    show sort order
tvsh    show name / TV show
©wrk    work name
©mvn    movement name
```

**Numeric pair atoms** (values are lists of tuples):
```
trkn    track number: [(track_number, total_tracks)]
disk    disc number: [(disc_number, total_discs)]
```

**Integer atoms** (values are lists of ints):
```
tmpo    BPM
©mvi    movement index
©mvc    movement count
rtng    content rating
stik    media kind (e.g. 1=Music, 6=Music Video)
```

**Boolean atoms**:
```
cpil    compilation (True/False)
pgap    gapless album
pcst    podcast flag
```

**Cover art**:
```
covr    list of MP4Cover objects (subclass of bytes with .imageformat attribute)
```

**Freeform atoms** (arbitrary key-value):
```
----:com.apple.iTunes:iTunNORM    ReplayGain (Apple format)
----:com.apple.iTunes:ISRC        ISRC code
----:com.apple.iTunes:LABEL       label
----:com.serato.dj:*              Serato data (see DJ software section)
```
Accessed as `audio["----:com.apple.iTunes:ISRC"]` — returns list of `MP4FreeForm` objects.

`MP4FreeForm`: subclass of bytes with `.dataformat` (int) and `.version` (int) attributes. The bytes ARE the value.

---

## Field Inventory

### Core Fields for DJ Library Import

| Field | Frame ID / key | Mutagen access | Type | MP3 | FLAC | AIFF | WAV | M4A | OGG | Prevalence in DJ files | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| title | TIT2 / TITLE / ©nam | `audio["TIT2"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Always if tags exist | |
| artist | TPE1 / ARTIST / ©ART | `audio["TPE1"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Always if tags exist | |
| album | TALB / ALBUM / ©alb | `audio["TALB"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Common | Often release title |
| label | TPUB / ORGANIZATION / ©too or ----:com.apple.iTunes:LABEL | `audio["TPUB"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Sometimes | Beatport populates; rips may not |
| catalogue_number | TXXX:CATALOGNUMBER / CATALOGNUMBER | `audio["TXXX:CATALOGNUMBER"].text[0]` | str | TXXX | VC | TXXX | TXXX | freeform | VC | Rare | Not a standard ID3 frame |
| year | TDRC/TYER / DATE / ©day | `audio["TDRC"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Common | TYER (v2.3) or TDRC (v2.4); partial dates possible |
| bpm | TBPM / BPM / tmpo | `audio["TBPM"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Common on store downloads | May be absent; may be integer or decimal string |
| key | TKEY / INITIALKEY / ---- | `audio["TKEY"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Sometimes | Notation varies (see reliability) |
| genre | TCON / GENRE / ©gen | `audio["TCON"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Common | Often freeform or store taxonomy (see reliability) |
| track_number | TRCK / TRACKNUMBER / trkn | `audio["TRCK"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Common | May include total: "3/12" |
| isrc | TSRC / ISRC / ----:com.apple.iTunes:ISRC | `audio["TSRC"].text[0]` | str | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Sometimes on major releases | Sparse on independent electronic music |
| comment | COMM / COMMENT / ©cmt | `audio.tags.getall("COMM")` | list of COMM frames | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Sometimes | COMM frames have lang + desc; check `COMM::eng` |
| duration | `.info.length` | `audio.info.length` | float (seconds) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Always | From audio stream, not tags |
| bitrate | `.info.bitrate` | `audio.info.bitrate` | int (bps) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Always | From audio stream |
| sample_rate | `.info.sample_rate` | `audio.info.sample_rate` | int (Hz) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Always | From audio stream |
| channels | `.info.channels` | `audio.info.channels` | int | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Always | From audio stream |
| bits_per_sample | `.info.bits_per_sample` | `audio.info.bits_per_sample` | int | No | ✓ | ✓ | ✓ | ✓ | No | Always (for formats that have it) | N/A for MP3 (lossy) |

### Fallback and Access Notes

When accessing tags defensively in an import pipeline, every `.tags["FRAME"]` access must be wrapped in a try/except or a prior check. Key lookups raise `KeyError` if the frame is absent. Recommended pattern:

```
# Get title safely:
tags = audio.tags
title = str(tags["TIT2"]) if tags and "TIT2" in tags else None

# Get TPUB (label) — common alternatives:
label = None
if tags:
    if "TPUB" in tags:
        label = tags["TPUB"].text[0]
    elif "TXXX:LABEL" in tags:
        label = tags["TXXX:LABEL"].text[0]

# For FLAC:
label = audio.get("ORGANIZATION", [None])[0]   # or LABEL key

# TDRC vs TYER:
year = None
if tags:
    if "TDRC" in tags:
        year = str(tags["TDRC"].text[0])[:4]    # truncate to year only
    elif "TYER" in tags:
        year = tags["TYER"].text[0]
```

---

## Tag Reliability in DJ Libraries

### MP3 from Beatport

Beatport is the most reliable source for DJ library metadata. Downloads include:
- TIT2 (title): always present, usually accurate
- TPE1 (artist): always present
- TALB (album/release title): always present
- TPUB (label): present and reliable — Beatport is strong on label data
- TCON (genre): present; uses Beatport's own taxonomy (e.g. "Techno (Raw / Deep / Hypnotic)", "House"), not standardised
- TBPM (BPM): present; Beatport uses their own BPM analysis. May be stored as integer string ("128") or decimal string ("128.00") — both are common. Accuracy is generally good for 4/4 material but may be wrong by a factor of 2 for half-time/double-time feels
- TKEY (key): present on most tracks; written in Beatport's notation which is traditional musical notation (e.g. "A minor", "F# major") — not Camelot, not Open Key. Beatport Pro reportedly writes Open Key notation to a TXXX:TKY2 field and traditional to TKEY
- TDRC or TYER (year): present (original release year or Beatport upload date — may differ)
- APIC (cover art): present, typically JPEG 500×500 or larger
- TSRC (ISRC): sometimes present on major-label releases; often absent on independent electronic releases
- TPUB or TXXX:CATALOGNUMBER: catalogue number handling is inconsistent across Beatport download tools; not reliable from the native download

### MP3 from Juno, Traxsource, Bandcamp

Similar to Beatport for core fields. Differences:
- Juno: label and catalogue number generally present; TCON uses their own genres
- Traxsource: strong on label, BPM, genre for house/techno; uses their own genre taxonomy
- Bandcamp: artist/title/album present; label often absent or set to artist name; TBPM often absent unless artist set it; TCON inconsistent
- None of these sources consistently write TKEY or TSRC

### FLAC from Beatport or Bandcamp

Beatport's FLAC downloads mirror their MP3 tags using Vorbis Comment keys. Coverage is similar but field names differ: ARTIST, TITLE, ALBUM, ORGANIZATION (label), GENRE, BPM, DATE, TRACKNUMBER. Beatport FLAC downloads are reliable for core fields.

Bandcamp FLAC: uses ARTIST, TITLE, ALBUM, DATE, TRACKNUMBER, GENRE reliably; ORGANIZATION often absent.

### MP3 Rips of Vinyl

Highly variable. May have:
- Only ID3v1 tags (30-char truncated artist/title from ripping software)
- Manually entered ID3v2 tags of unknown quality
- No tags at all (`.tags` is None)
- Tags entered by ripping software that guesses artist/title from filename

TBPM, TKEY, TPUB: typically absent. APIC: typically absent. TSRC: absent.

### AIFF Files (Traktor users)

DJ-grade AIFF files are typically sourced from stores (Beatport, Traxsource) or ripped from CD. Tag quality mirrors the source. AIFF files from Traktor users may have been written back by Traktor with `PRIV:TRAKTOR4` but standard fields should be untouched unless the user edited them.

Known issue: some AIFF files have empty or malformed ID3 chunks. mutagen handles this via `ID3NoHeaderError`.

### WAV Files

WAV metadata is the least reliable format:
- Many WAV files have no tags at all
- The standard (RIFF INFO chunks) is not supported by mutagen
- Some WAV files have an ID3 chunk (written by Rekordbox, Traktor, some DAWs) that mutagen can read
- Some WAV files have both a RIFF INFO chunk AND an ID3 chunk; mutagen reads only the ID3 chunk and ignores RIFF INFO
- Rekordbox exports WAV to USB with RIFF INFO chunks, not ID3 — these will have `tags = None` in mutagen

For a DJ library, WAV files should be treated as potentially tagless. Always fall back to filename parsing.

### Files Processed by Traktor / Rekordbox / Serato

- Standard text tags are generally preserved unchanged
- DJ software adds its own proprietary frames/keys without overwriting standard fields
- Exception: Serato may overwrite COMM (comment) with purchase info in older versions
- Exception: Some tools rewrite BPM with their own analysis result into TBPM
- Exception: Rekordbox optionally writes TKEY when analysis is done

### TBPM Reliability

- Integer vs decimal: both are used. ID3 spec says numeric string. Beatport writes "128" or "128.00". Mixed In Key writes with decimals. DJ analysis software (Traktor, Rekordbox) writes integers. TBPM spec says numeric — treat as a float after parsing.
- Accuracy: varies. Beatport BPM values are metadata provided by labels, not independently analysed — some are wrong. DJ software BPM analysis is generally accurate for 4/4 techno/house in the 120–150 BPM range.
- Absence: common in vinyl rips, old MP3s, Bandcamp downloads
- Serato Autotags: Serato stores its own BPM in the binary GEOB; TBPM may or may not match

### TKEY Reliability

This is the most inconsistent field in DJ libraries:

| Notation system | Example | Used by |
|---|---|---|
| Traditional musical | "A minor", "F# major", "Db major" | Rekordbox (when enabled), Beatport TKEY, standard |
| Camelot Wheel | "8A", "12B", "1A" | Mixed In Key (writes to TXXX:INITIALKEY and TKEY) |
| Open Key Notation | "8m", "12d", "1m" | Traktor |
| Abbreviated traditional | "Am", "F#maj" | Various taggers |

A library with tracks from multiple sources will have all four notations in TKEY. There is no programmatic way to distinguish "A" (A major in some notations) from "A" used as a Camelot key code without context. Plan to handle normalisation.

Absence is common. TKEY is absent in many files.

### TCON Reliability

TCON can contain:
- A numeric genre index in parentheses (ID3v1 legacy format): `(17)` = Rock
- A freeform string: `"Techno"`, `"Techno (Raw / Deep / Hypnotic)"`, `"Dark Techno"`
- Multiple genres (ID3v2.4 only): null-separated list
- A mix: `(17)Rock` = Rock genre + "Rock" as suffix

For a DJ library, TCON is almost always a freeform string reflecting the store's genre taxonomy. Not standardised across sources. Useful as a coarse signal but not reliable for exact matching.

---

## Full Tag Read Flow

1. **Open file**: call `mutagen.File(path)`. Format detection reads the file header bytes.

2. **Check return value**: if `None`, the file is not a recognised audio format (or is corrupt). Log and skip.

3. **Check `.tags`**: if `None`, no tag block is present in the file. Audio properties (`.info`) are still available. For DJ files this means no title/artist — fall back to filename parsing.

4. **Determine tag format**: check `type(audio.tags)` if format-specific behaviour is needed. `ID3` for MP3/AIFF/WAV, `VComment`/`OggVCommentDict` for FLAC/OGG, `MP4Tags` for M4A.

5. **Read text tags (ID3)**: access each frame by key. Every access that might be absent must be wrapped in a check or try/except. For TYER vs TDRC: check TDRC first (v2.4); if absent check TYER (v2.3). Cast frame text to string with `str(frame)` or use `.text[0]` for the first value.

6. **Read text tags (FLAC/OGG VorbisComment)**: access as `audio.get("TITLE", [None])[0]`. Keys are case-insensitive in spec but stored as written; use uppercase by convention.

7. **Read text tags (MP4)**: access as `audio.get("©nam", [None])[0]`. Types vary by atom — trkn returns `[(track, total)]`, tmpo returns `[int]`.

8. **Read audio properties**: `audio.info.length`, `audio.info.bitrate`, `audio.info.sample_rate`, `audio.info.channels`. Always present (never None) for valid audio files. MP3 additionally has `.info.bitrate_mode`, `.info.encoder_info`, `.info.sketchy`.

9. **Read cover art (ID3)**: `audio.tags.getall("APIC")` if APIC frames needed. Filter for `.type == 3` to get front cover. `.data` is raw bytes.

10. **Read cover art (FLAC)**: `audio.pictures`. Filter for `.type == 3`.

11. **Read cover art (MP4)**: `audio.tags.get("covr", [])`. List of MP4Cover objects.

12. **Handle GEOB (if DJ software data needed)**: `audio.tags.getall("GEOB")`. Each has `.desc` and `.data` (binary). Parsing requires format-specific code per DJ software.

13. **Format-specific differences**:
    - WAV: `.tags` may be None even for valid audio (no ID3 chunk). RIFF INFO is not accessible.
    - AIFF: same ID3 interface as MP3 but stored in IFF chunk. `.info.bits_per_sample` is available.
    - FLAC: `.pictures` is separate from `.tags`. StreamInfo is richer (bits_per_sample, total_samples).
    - M4A: trkn/disk return tuples, not strings. tmpo returns int.

14. **Handle missing fields gracefully**: every optional field should default to `None` at the Python level. The pipeline should never crash on a missing tag.

---

## Encoding Issues and Edge Cases

**Files with no tags**: `audio.tags` is `None`. `audio.info` is always populated for valid audio. No exception is raised; check for `None` before any tag access.

**Corrupted tags**: mutagen raises `mutagen.MutagenError` (or a subclass) for serious corruption. For minor corruption (unknown frames, truncated frames), it logs a warning and skips the bad frame. `mutagen.File()` will return a partial result where parseable frames are present and bad ones are omitted — it does not raise on a single bad frame.

**ID3NoHeaderError**: raised when using `mutagen.id3.ID3(filename)` directly on a file without an ID3 header. Not raised by `mutagen.File()` (returns the FileType object with `tags = None` instead).

**ID3v1 Latin-1 encoding issues**: ID3v1 fields are Latin-1. Non-Latin-1 characters in v1 tags result in encoding errors or replacement characters depending on the source. mutagen reads them as Latin-1; for a library of electronic music (mostly ASCII artist/title names) this is rarely a problem.

**ID3v2.3 frames with v2.4 encoding**: some files have an ID3v2.3 header but use UTF-8 (encoding byte 3), which is technically only valid in v2.4. mutagen parses these pragmatically rather than strictly — it reads the encoding byte and uses UTF-8 regardless of the header version.

**Files with both ID3v2 and APEv2**: for formats where both can appear (MP3, TrueAudio), `mutagen.mp3.MP3` reads only the ID3 tag. APEv2 on an MP3 file is accessible via `mutagen.apev2.APEv2(filename)` directly, but this is unusual. For a DJ library of downloaded tracks, this scenario is rare.

**Large APIC frames**: mutagen loads the entire tag into memory, including all APIC frames. A 1,000-track batch read where each track has a 500 KB cover will load ~500 MB of image data. For an import pipeline where images are not needed, filter out APIC frames after reading or use a streaming approach. Historical bugs with very large APIC frames are believed fixed as of v1.10.

**Truncated or zero-length frames**: frames with a declared length of 0 are silently skipped by mutagen. Truncated files (where the file ends mid-tag) cause a `MutagenError`.

**TXXX description case sensitivity**: mutagen treats TXXX descriptions as case-sensitive for key lookup. `audio.tags["TXXX:BPM"]` and `audio.tags["TXXX:bpm"]` are different keys. The ID3 spec is ambiguous on case sensitivity for TXXX descriptions. Different taggers write in different cases. Always check both if needed, or use `audio.tags.getall("TXXX")` and search the `.desc` attribute case-insensitively.

**TXXX:INITIALKEY vs TKEY**: some tools write the key to TKEY, some to TXXX:INITIALKEY, some to both. Check both fields. They may contain values in different notations.

**`mutagen.File()` on non-audio files**: returns `None` for PDFs, ZIPs, images, etc. Does not raise. Wrap in a check.

**Multiple APIC frames with same PictureType**: technically invalid per spec (should use different descriptions). mutagen reads multiple APIC frames with type=3 without error; `audio.tags.getall("APIC")` returns all of them.

**WAVE ID3 chunk case variation**: the RIFF chunk used to store ID3 in WAV files may be named `"ID3 "` (uppercase) or `"id3 "` (lowercase). mutagen handles both spellings.

**TCON numeric genre codes**: if TCON contains `"(17)"`, this is the ID3v1 genre index 17 = "Rock". mutagen exposes it as the raw string `"(17)"` — it does not translate to genre name. A lookup table of the 192 ID3v1 genres is needed if human-readable genre names are required from old files.

---

## Installation

```
uv add mutagen
```

No OS-level dependencies. No C extensions. Works on Windows, Linux, macOS. Works in WSL2.

Python requirement: 3.10+. The package is a pure Python wheel (`py3-none-any.whl`). The latest stable version is 1.47.0 (September 2023).

Minimal verification script (print all tags and audio properties for MP3, FLAC, AIFF):

```python
import sys
import mutagen

PATHS = [
    "test.mp3",
    "test.flac",
    "test.aiff",
]

for path in PATHS:
    print(f"\n--- {path} ---")
    audio = mutagen.File(path)
    if audio is None:
        print("  [not recognised]")
        continue

    print(f"  type: {type(audio).__name__}")
    print(f"  info.length: {audio.info.length:.2f}s")
    print(f"  info.bitrate: {audio.info.bitrate}")
    print(f"  info.sample_rate: {audio.info.sample_rate}")
    print(f"  info.channels: {audio.info.channels}")

    if hasattr(audio.info, "bits_per_sample"):
        print(f"  info.bits_per_sample: {audio.info.bits_per_sample}")

    if audio.tags is None:
        print("  tags: None (no tag block)")
    else:
        print(f"  tag type: {type(audio.tags).__name__}")
        for key in sorted(audio.tags.keys()):
            try:
                val = audio.tags[key]
                print(f"  {key}: {val}")
            except Exception as e:
                print(f"  {key}: [error: {e}]")
```

Run with: `uv run python verify_mutagen.py`

**Known issues on Windows (not WSL2)**:
- mutagen itself works natively on Windows — no issues
- Essentia (separate library) does NOT work on native Windows — use WSL2 for Essentia
- mutagen has no dependency on Essentia; the two are independent in the import pipeline

---

## Open Questions

1. **Catalogue number field name in FLAC**: Is `CATALOGNUMBER` the correct Vorbis Comment key for catalogue numbers in electronic music files from Beatport/Juno, or is `LABELNO` or `LABEL_NUMBER` used? Confirm against actual downloads.

2. **Beatport TKEY notation in FLAC**: Beatport FLAC Vorbis Comment `BPM` and `INITIALKEY` — are these the exact key names used, and is the notation traditional musical or Camelot? Validate against actual Beatport FLAC downloads.

3. **Serato TBPM vs Serato Autotags BPM consistency**: Under what exact conditions does Serato DJ write BPM to TBPM? Is this a setting, a version difference, or format-dependent? Validate against files analysed by Serato.

4. **Rekordbox TKEY notation**: Rekordbox writes key to TKEY when enabled — confirm whether it writes traditional notation ("A minor") or abbreviated ("Am"). Validate against actual Rekordbox-analysed files.

5. **TXXX:CATALOGNUMBER vs TXXX:CATALOGID**: the Mp3tag community discussion references both `CATALOGNUMBER` and `CATALOGID` as TXXX descriptions. Which is more common in actual DJ library files? Is there a de facto standard?

6. **WAV files from Rekordbox USB export**: Rekordbox exports WAV to USB with RIFF INFO chunks — confirming that `audio.tags` will be `None` for these files in mutagen. This must be validated against actual Rekordbox USB exports. If RIFF INFO support becomes necessary, consider a fallback parser (e.g., using `struct` to parse the RIFF INFO chunk directly, outside mutagen).

7. **Serato BPM binary format in GEOB:Serato Autotags**: the Holzhaus/serato-tags repository claims "BPM and Gain values" are documented as complete. Confirm the exact byte layout if Serato BPM is needed as a fallback when TBPM is absent.

8. **mutagen v2.3 save behaviour**: when `mutagen.File()` opens an ID3v2.3 file with `translate=True` (default), frames are upgraded to v2.4 equivalents in memory. Does this mean a naive `audio.save()` call will convert the file from v2.3 to v2.4? Confirm and document the correct pattern for a read-only pipeline (no `save()` calls solves this, but verify).

9. **Ogg Vorbis bitrate attributes**: the nominal bitrate is exposed as `audio.info.bitrate`. Confirm whether lower-bound and upper-bound bitrate fields from the Vorbis header are exposed anywhere in mutagen's API for VBR Ogg files.

10. **mutagen version currency**: v1.47.0 is September 2023. Check for newer releases before implementing the pipeline — there may be a v1.48 or later.
