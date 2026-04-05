"""
mutagen tag reader for the Crate import pipeline.

Public API: read_tags(path) -> dict

Returns a flat dict of raw tag values and audio stream properties for a single
audio file. Never raises to the caller — all errors are captured in the returned dict.
Never writes to the file.
"""

import logging
import os
from pathlib import Path

import mutagen
import mutagen.aiff
import mutagen.flac
import mutagen.mp3
import mutagen.mp4
import mutagen.oggvorbis
import mutagen.wave

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_txxx(tags, description: str) -> str | None:
    """Return the text of the first TXXX frame matching description (case-insensitive)."""
    for frame in tags.getall("TXXX"):
        if frame.desc.lower() == description.lower():
            return frame.text[0] if frame.text else None
    return None


def _error_dict(path: str, file_format: str, error_msg: str) -> dict:
    """Return a fully-populated dict with all keys set to None/False and the given error."""
    return {
        # File identity
        "file_path": path,
        "file_format": file_format,
        # Audio stream properties
        "duration_seconds": None,
        "bitrate_bps": None,
        "bitrate_mode": None,
        "sample_rate_hz": None,
        "channels": None,
        "bits_per_sample": None,
        "encoder_info": None,
        "is_sketchy": None,
        # Core text fields
        "tag_title": None,
        "tag_artist": None,
        "tag_album_artist": None,
        "tag_album": None,
        "tag_label": None,
        "tag_catalogue_no": None,
        "tag_genre": None,
        "tag_comment": None,
        "tag_isrc": None,
        "tag_copyright": None,
        # Date / year
        "tag_year_id3v24": None,
        "tag_year_id3v23": None,
        "tag_date_released": None,
        "tag_date_original": None,
        "tag_date_vorbis": None,
        "tag_date_mp4": None,
        # Track / disc numbering
        "tag_track_number": None,
        "tag_disc_number": None,
        # DJ-relevant fields
        "tag_bpm": None,
        "tag_key": None,
        "tag_energy": None,
        "tag_initial_key_txxx": None,
        # Cover art detection
        "has_embedded_art": False,
        # DJ software detection
        "has_serato_tags": False,
        "has_traktor_tags": False,
        "has_rekordbox_tags": False,
        # Tag metadata
        "tag_id3_version": None,
        "tag_format_type": "none",
        # Error / status
        "tags_error": error_msg,
        "tags_present": False,
    }


def _extract_audio_properties(audio, file_format: str) -> dict:
    """Extract audio stream properties from audio.info into a dict."""
    info = audio.info
    props = {
        "duration_seconds": info.length,
        "bitrate_bps": info.bitrate,
        "sample_rate_hz": info.sample_rate,
        "channels": info.channels,
        "bits_per_sample": getattr(info, "bits_per_sample", None),
        "bitrate_mode": None,
        "encoder_info": None,
        "is_sketchy": None,
    }
    if file_format == "mp3":
        _mode_names = {
            int(mutagen.mp3.BitrateMode.CBR): "CBR",
            int(mutagen.mp3.BitrateMode.VBR): "VBR",
            int(mutagen.mp3.BitrateMode.ABR): "ABR",
            int(mutagen.mp3.BitrateMode.UNKNOWN): "UNKNOWN",
        }
        props["bitrate_mode"] = _mode_names.get(int(info.bitrate_mode), "UNKNOWN")
        raw_encoder = info.encoder_info
        props["encoder_info"] = raw_encoder if raw_encoder else None
        props["is_sketchy"] = info.sketchy
    return props


# ---------------------------------------------------------------------------
# Format-specific extractors
# ---------------------------------------------------------------------------


def _extract_id3(audio, path: str, file_format: str) -> dict:
    """Extract tags and properties from an ID3-tagged file (MP3, AIFF, WAV)."""
    result = _error_dict(path, file_format, None)
    result["tag_format_type"] = "id3"

    # Audio properties — always available for a valid file
    result.update(_extract_audio_properties(audio, file_format))

    tags = audio.tags
    tags_present = tags is not None
    result["tags_present"] = tags_present
    result["tags_error"] = None

    if not tags_present:
        # WAV without an ID3 chunk: valid audio, no tags — not an error
        return result

    # ID3 version
    result["tag_id3_version"] = ".".join(str(v) for v in tags.version)

    # Core text fields
    result["tag_title"] = tags["TIT2"].text[0] if "TIT2" in tags else None
    result["tag_artist"] = tags["TPE1"].text[0] if "TPE1" in tags else None
    result["tag_album_artist"] = tags["TPE2"].text[0] if "TPE2" in tags else None
    result["tag_album"] = tags["TALB"].text[0] if "TALB" in tags else None
    result["tag_label"] = tags["TPUB"].text[0] if "TPUB" in tags else None
    result["tag_genre"] = tags["TCON"].text[0] if "TCON" in tags else None
    result["tag_isrc"] = tags["TSRC"].text[0] if "TSRC" in tags else None
    result["tag_copyright"] = tags["TCOP"].text[0] if "TCOP" in tags else None
    result["tag_track_number"] = tags["TRCK"].text[0] if "TRCK" in tags else None
    result["tag_disc_number"] = tags["TPOS"].text[0] if "TPOS" in tags else None
    result["tag_bpm"] = tags["TBPM"].text[0] if "TBPM" in tags else None
    result["tag_key"] = tags["TKEY"].text[0] if "TKEY" in tags else None

    # COMM: prefer frame with empty .desc, fall back to first frame overall
    comm_frames = tags.getall("COMM")
    if comm_frames:
        selected = next((f for f in comm_frames if f.desc == ""), comm_frames[0])
        result["tag_comment"] = selected.text[0] if selected.text else None

    # Date / year fields
    result["tag_year_id3v24"] = tags["TDRC"].text[0] if "TDRC" in tags else None
    result["tag_year_id3v23"] = tags["TYER"].text[0] if "TYER" in tags else None
    result["tag_date_released"] = tags["TDRL"].text[0] if "TDRL" in tags else None
    if "TDOR" in tags:
        result["tag_date_original"] = tags["TDOR"].text[0]
    elif "TORY" in tags:
        result["tag_date_original"] = tags["TORY"].text[0]

    # TXXX fields
    result["tag_catalogue_no"] = _get_txxx(tags, "CATALOGNUMBER") or _get_txxx(tags, "CATALOGID")
    result["tag_initial_key_txxx"] = _get_txxx(tags, "INITIALKEY")
    result["tag_energy"] = _get_txxx(tags, "ENERGY")

    # Cover art detection — iterate keys, avoid getall("APIC")
    for key in tags:
        if key.startswith("APIC:") or key == "APIC:":
            frame = tags[key]
            if frame.type == 3:  # PictureType.COVER_FRONT
                result["has_embedded_art"] = True
                break

    # DJ software detection
    result["has_serato_tags"] = any(k.startswith("GEOB:Serato") for k in tags)
    result["has_traktor_tags"] = "PRIV:TRAKTOR4" in tags
    result["has_rekordbox_tags"] = any(
        "rekordbox" in k.lower() for k in tags if k.startswith("GEOB:")
    )

    return result


def _extract_vorbis(audio, path: str, file_format: str) -> dict:
    """Extract tags and properties from a VorbisComment file (FLAC, OGG)."""
    result = _error_dict(path, file_format, None)
    result["tag_format_type"] = "vorbiscomment"

    result.update(_extract_audio_properties(audio, file_format))

    tags = audio.tags
    tags_present = tags is not None
    result["tags_present"] = tags_present
    result["tags_error"] = None

    if not tags_present:
        return result

    def _get(key: str) -> str | None:
        vals = audio.get(key, [])
        return vals[0] if vals else None

    def _get_joined(key: str) -> str | None:
        vals = audio.get(key, [])
        return " / ".join(vals) if vals else None

    # Core text fields
    result["tag_title"] = _get("TITLE")
    result["tag_artist"] = _get_joined("ARTIST")
    result["tag_album_artist"] = _get("ALBUMARTIST")
    result["tag_album"] = _get("ALBUM")
    # Label: ORGANIZATION primary, LABEL fallback
    result["tag_label"] = _get("ORGANIZATION") or _get("LABEL")
    result["tag_catalogue_no"] = _get("CATALOGNUMBER")
    result["tag_genre"] = _get_joined("GENRE")
    result["tag_comment"] = _get("COMMENT")
    result["tag_isrc"] = _get("ISRC")
    result["tag_copyright"] = _get("COPYRIGHT")
    result["tag_track_number"] = _get("TRACKNUMBER")
    result["tag_disc_number"] = _get("DISCNUMBER")
    result["tag_bpm"] = _get("BPM")
    result["tag_key"] = _get("KEY")
    result["tag_initial_key_txxx"] = _get("INITIALKEY")
    result["tag_energy"] = _get("ENERGY")
    result["tag_date_vorbis"] = _get("DATE")

    # Cover art — FLAC has .pictures; OGG does not
    if hasattr(audio, "pictures") and audio.pictures:
        result["has_embedded_art"] = any(p.type == 3 for p in audio.pictures)

    # DJ software detection — Serato writes SERATO_* keys to VorbisComment
    result["has_serato_tags"] = any(
        k.upper().startswith("SERATO_") for k in (audio.keys() if tags else [])
    )
    # Traktor and Rekordbox use ID3 PRIV/GEOB frames; not applicable to VorbisComment
    result["has_traktor_tags"] = False
    result["has_rekordbox_tags"] = False

    return result


def _extract_mp4(audio, path: str, file_format: str) -> dict:
    """Extract tags and properties from an MP4/M4A file."""
    result = _error_dict(path, file_format, None)
    result["tag_format_type"] = "mp4"

    result.update(_extract_audio_properties(audio, file_format))

    # MP4 always has a tag container (MP4Tags), but it may be effectively empty.
    # audio.tags can be None for malformed files.
    tags = audio.tags
    tags_present = tags is not None
    result["tags_present"] = tags_present
    result["tags_error"] = None

    if not tags_present:
        return result

    def _freeform(key: str) -> str | None:
        raw = audio.get(key, [None])[0]
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        # MP4FreeForm is a subclass of bytes
        try:
            return raw.decode("utf-8", errors="replace")
        except AttributeError:
            return str(raw)

    # Core text fields
    result["tag_title"] = audio.get("©nam", [None])[0]
    result["tag_artist"] = audio.get("©ART", [None])[0]
    result["tag_album_artist"] = audio.get("aART", [None])[0]
    result["tag_album"] = audio.get("©alb", [None])[0]
    result["tag_genre"] = audio.get("©gen", [None])[0]
    result["tag_comment"] = audio.get("©cmt", [None])[0]
    result["tag_copyright"] = audio.get("cprt", [None])[0]
    result["tag_date_mp4"] = audio.get("©day", [None])[0]

    # Label: ©pub primary, freeform LABEL fallback
    label = audio.get("©pub", [None])[0]
    if label is None:
        label = _freeform("----:com.apple.iTunes:LABEL")
    result["tag_label"] = label

    # Freeform atoms
    result["tag_catalogue_no"] = _freeform("----:com.apple.iTunes:CATALOGNUMBER")
    result["tag_isrc"] = _freeform("----:com.apple.iTunes:ISRC")
    result["tag_key"] = _freeform("----:com.apple.iTunes:KEY")

    # Numeric atoms — convert to string for type consistency
    trkn = audio.get("trkn", [None])[0]
    if trkn:
        result["tag_track_number"] = f"{trkn[0]}/{trkn[1]}" if trkn[1] else str(trkn[0])

    disk = audio.get("disk", [None])[0]
    if disk:
        result["tag_disc_number"] = f"{disk[0]}/{disk[1]}" if disk[1] else str(disk[0])

    tmpo = audio.get("tmpo", [None])[0]
    result["tag_bpm"] = str(tmpo) if tmpo is not None else None

    # Cover art
    covr = audio.get("covr", [])
    result["has_embedded_art"] = len(covr) > 0

    # DJ software detection: not applicable to MP4
    result["has_serato_tags"] = False
    result["has_traktor_tags"] = False
    result["has_rekordbox_tags"] = False

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_tags(path: str | Path) -> dict:
    """
    Open a single audio file with mutagen and return a flat dict of raw tag values
    and audio stream properties.

    Never raises. All error conditions are captured and returned in the dict.
    Never writes to the file.
    """
    str_path = os.fspath(path)
    file_format = "unknown"

    try:
        audio = mutagen.File(str_path)

        if audio is None:
            logger.warning("mutagen.File returned None for %s — unrecognised format", str_path)
            return _error_dict(str_path, "unknown", "unrecognised format")

        if isinstance(audio, mutagen.mp3.MP3):
            file_format = "mp3"
            return _extract_id3(audio, str_path, file_format)

        elif isinstance(audio, mutagen.flac.FLAC):
            file_format = "flac"
            return _extract_vorbis(audio, str_path, file_format)

        elif isinstance(audio, mutagen.aiff.AIFF):
            file_format = "aiff"
            return _extract_id3(audio, str_path, file_format)

        elif isinstance(audio, mutagen.wave.WAVE):
            file_format = "wav"
            return _extract_id3(audio, str_path, file_format)

        elif isinstance(audio, mutagen.mp4.MP4):
            file_format = "m4a"
            return _extract_mp4(audio, str_path, file_format)

        elif isinstance(audio, mutagen.oggvorbis.OggVorbis):
            file_format = "ogg"
            return _extract_vorbis(audio, str_path, file_format)

        else:
            file_format = "unknown"
            logger.warning("Unsupported format for %s: %s", str_path, type(audio).__name__)
            return _error_dict(str_path, file_format, "unsupported format")

    except mutagen.MutagenError as e:
        logger.warning("MutagenError reading %s: %s", str_path, e)
        return _error_dict(str_path, file_format, str(e))

    except Exception as e:
        logger.error("Unexpected error reading tags from %s: %s", str_path, e, exc_info=True)
        return _error_dict(str_path, "unknown", str(e))
