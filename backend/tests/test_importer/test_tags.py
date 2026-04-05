"""
Tests for backend/importer/tags.py

All mutagen interactions are mocked — no real audio files required.
Tests follow the plan in md/plans/plan-mutagen-importer.md.
"""

from unittest.mock import MagicMock, patch

import mutagen
import mutagen.aiff
import mutagen.flac
import mutagen.mp3
import mutagen.mp4
import mutagen.oggvorbis
import mutagen.wave

from backend.importer.tags import read_tags

# ---------------------------------------------------------------------------
# Mock info classes
# ---------------------------------------------------------------------------


class MockMPEGInfo:
    length = 300.0
    bitrate = 320000
    sample_rate = 44100
    channels = 2
    bitrate_mode = 1  # BitrateMode.CBR == 1 (int subclass, no .name attribute)
    encoder_info = "LAME3.100"
    sketchy = False


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


class MockAIFFInfo:
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


# ---------------------------------------------------------------------------
# Mock frame factories
# ---------------------------------------------------------------------------


def make_id3_frame(text_value):
    frame = MagicMock()
    frame.text = [text_value]
    return frame


def make_txxx_frame(desc, text_value):
    frame = MagicMock()
    frame.desc = desc
    frame.text = [text_value]
    return frame


def make_comm_frame(desc, text_value):
    frame = MagicMock()
    frame.desc = desc
    frame.text = [text_value]
    return frame


def make_apic_frame(pic_type):
    frame = MagicMock()
    frame.type = pic_type
    return frame


def make_flac_picture(pic_type):
    pic = MagicMock()
    pic.type = pic_type
    return pic


def make_id3_tags(
    frames: dict, txxx_frames=None, comm_frames=None, apic_frames=None, extra_keys=None
):
    """
    Build a mock ID3 tags object.

    frames: dict mapping frame name -> text value
    txxx_frames: list of (desc, text) tuples
    comm_frames: list of (desc, text) tuples
    apic_frames: list of pic_type ints
    extra_keys: list of additional key strings to include in tags.keys()
    """
    tags = MagicMock()
    tags.version = (2, 3, 0)

    frame_objects = {}
    for name, value in frames.items():
        frame_objects[name] = make_id3_frame(value)

    # APIC frames
    apic_frame_objects = {}
    for i, pic_type in enumerate(apic_frames or []):
        key = f"APIC:{i}" if i > 0 else "APIC:"
        apic_frame_objects[key] = make_apic_frame(pic_type)

    # TXXX frames
    txxx_list = [make_txxx_frame(desc, text) for desc, text in (txxx_frames or [])]

    # COMM frames
    comm_list = [make_comm_frame(desc, text) for desc, text in (comm_frames or [])]

    all_keys = list(frame_objects.keys()) + list(apic_frame_objects.keys()) + (extra_keys or [])

    def contains(key):
        return key in frame_objects or key in apic_frame_objects or key in (extra_keys or [])

    tags.__contains__ = lambda self, key: contains(key)
    tags.__getitem__ = lambda self, key: frame_objects.get(key) or apic_frame_objects.get(key)
    tags.__iter__ = lambda self: iter(all_keys)
    tags.keys = lambda: all_keys
    tags.getall = lambda name: txxx_list if name == "TXXX" else comm_list if name == "COMM" else []

    return tags


# ---------------------------------------------------------------------------
# Helper: build a mock MP3 audio object
# ---------------------------------------------------------------------------


def make_mp3_audio(tags):
    audio = MagicMock(spec=mutagen.mp3.MP3)
    audio.info = MockMPEGInfo()
    audio.tags = tags
    return audio


def make_flac_audio(tags, pictures=None):
    audio = MagicMock(spec=mutagen.flac.FLAC)
    audio.info = MockFLACInfo()
    audio.tags = tags
    audio.pictures = pictures or []
    return audio


def make_wav_audio(tags):
    audio = MagicMock(spec=mutagen.wave.WAVE)
    audio.info = MockWAVInfo()
    audio.tags = tags
    return audio


def make_aiff_audio(tags):
    audio = MagicMock(spec=mutagen.aiff.AIFF)
    audio.info = MockAIFFInfo()
    audio.tags = tags
    return audio


def make_mp4_audio(data: dict):
    """data is passed to audio.get() calls."""
    audio = MagicMock(spec=mutagen.mp4.MP4)
    audio.info = MockMP4Info()
    # MP4 always has tags unless malformed
    audio.tags = MagicMock()
    audio.get = lambda key, default=None: data.get(key, default)
    return audio


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


def test_mp3_full_id3v24_tags():
    """MP3 with all major ID3v2.4 tags populates every output field."""
    tags = make_id3_tags(
        frames={
            "TIT2": "Test Track",
            "TPE1": "Test Artist",
            "TPE2": "Album Artist",
            "TALB": "Test Album",
            "TPUB": "Test Label",
            "TCON": "Techno",
            "TBPM": "130",
            "TKEY": "Am",
            "TSRC": "GBDUW2000001",
            "TCOP": "2020 Test",
            "TRCK": "3/12",
            "TPOS": "1/2",
            "TDRC": "2020-06-01",
            "TYER": "2020",
            "TDRL": "2020-06-15",
            "TDOR": "2019",
        },
        txxx_frames=[("CATALOGNUMBER", "TEST001"), ("INITIALKEY", "11A"), ("ENERGY", "8")],
        comm_frames=[("", "Great track")],
        apic_frames=[3],
        extra_keys=["GEOB:Serato Analysis", "PRIV:TRAKTOR4"],
    )
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tags_present"] is True
    assert result["tags_error"] is None
    assert result["file_format"] == "mp3"
    assert result["tag_format_type"] == "id3"
    assert result["tag_title"] == "Test Track"
    assert result["tag_artist"] == "Test Artist"
    assert result["tag_album_artist"] == "Album Artist"
    assert result["tag_album"] == "Test Album"
    assert result["tag_label"] == "Test Label"
    assert result["tag_genre"] == "Techno"
    assert result["tag_bpm"] == "130"
    assert result["tag_key"] == "Am"
    assert result["tag_isrc"] == "GBDUW2000001"
    assert result["tag_copyright"] == "2020 Test"
    assert result["tag_track_number"] == "3/12"
    assert result["tag_disc_number"] == "1/2"
    assert result["tag_year_id3v24"] == "2020-06-01"
    assert result["tag_year_id3v23"] == "2020"
    assert result["tag_date_released"] == "2020-06-15"
    assert result["tag_date_original"] == "2019"
    assert result["tag_catalogue_no"] == "TEST001"
    assert result["tag_initial_key_txxx"] == "11A"
    assert result["tag_energy"] == "8"
    assert result["tag_comment"] == "Great track"
    assert result["has_embedded_art"] is True
    assert result["has_serato_tags"] is True
    assert result["has_traktor_tags"] is True
    # Audio properties
    assert result["duration_seconds"] == 300.0
    assert result["bitrate_bps"] == 320000
    assert result["sample_rate_hz"] == 44100
    assert result["channels"] == 2
    assert result["bitrate_mode"] == "CBR"
    assert result["encoder_info"] == "LAME3.100"
    assert result["is_sketchy"] is False


def test_mp3_id3v23_tyer_only():
    """MP3 with TYER but no TDRC stores year in tag_year_id3v23, tag_year_id3v24 is None."""
    tags = make_id3_tags(frames={"TYER": "2019"})
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_year_id3v23"] == "2019"
    assert result["tag_year_id3v24"] is None


def test_flac_vorbiscomment():
    """FLAC with VorbisComment keys maps to correct output fields."""

    class MockFLACAudio(MagicMock):
        pass

    audio = MagicMock(spec=mutagen.flac.FLAC)
    audio.info = MockFLACInfo()
    audio.tags = MagicMock()
    audio.pictures = []

    store = {
        "TITLE": ["FLAC Track"],
        "ARTIST": ["Artist One"],
        "ALBUM": ["FLAC Album"],
        "ORGANIZATION": ["Label One"],
        "DATE": ["2021"],
        "BPM": ["128"],
        "KEY": ["Fm"],
        "TRACKNUMBER": ["5"],
        "DISCNUMBER": ["1"],
        "CATALOGNUMBER": ["CAT002"],
        "COMMENT": ["Nice one"],
        "ISRC": ["GB123456789"],
    }
    audio.get = lambda key, default=None: store.get(key, default if default is not None else [])
    audio.keys = lambda: list(store.keys())

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.flac")

    assert result["file_format"] == "flac"
    assert result["tag_format_type"] == "vorbiscomment"
    assert result["tag_title"] == "FLAC Track"
    assert result["tag_artist"] == "Artist One"
    assert result["tag_label"] == "Label One"
    assert result["tag_date_vorbis"] == "2021"
    assert result["tag_bpm"] == "128"
    assert result["tag_key"] == "Fm"
    assert result["tag_catalogue_no"] == "CAT002"
    assert result["tag_comment"] == "Nice one"
    assert result["tag_isrc"] == "GB123456789"
    # ID3-specific fields must be None
    assert result["tag_year_id3v23"] is None
    assert result["tag_year_id3v24"] is None
    assert result["tag_date_released"] is None
    assert result["tag_date_original"] is None
    assert result["tag_id3_version"] is None


def test_m4a_mp4_atoms():
    """M4A with standard MP4 atoms converts trkn/disk tuples and tmpo int to strings."""
    data = {
        "©nam": ["M4A Track"],
        "©ART": ["M4A Artist"],
        "aART": ["Album Artist"],
        "©alb": ["M4A Album"],
        "©gen": ["House"],
        "©cmt": ["Comment"],
        "cprt": ["2021 Label"],
        "©day": ["2019-06-21"],
        "trkn": [(3, 12)],
        "disk": [(1, 2)],
        "tmpo": [128],
        "covr": [b"\xff\xd8"],  # non-empty — cover art present
    }
    audio = make_mp4_audio(data)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.m4a")

    assert result["file_format"] == "m4a"
    assert result["tag_format_type"] == "mp4"
    assert result["tag_title"] == "M4A Track"
    assert result["tag_track_number"] == "3/12"
    assert result["tag_disc_number"] == "1/2"
    assert result["tag_bpm"] == "128"
    assert result["tag_date_mp4"] == "2019-06-21"
    assert result["has_embedded_art"] is True
    # ID3-specific fields must be None
    assert result["tag_year_id3v23"] is None
    assert result["tag_year_id3v24"] is None
    assert result["tag_date_released"] is None
    assert result["tag_date_original"] is None
    assert result["tag_date_vorbis"] is None
    assert result["tag_id3_version"] is None
    assert result["tag_initial_key_txxx"] is None


def test_aiff_uses_id3_extraction():
    """AIFF file uses the ID3 extraction path and reports file_format='aiff'."""
    tags = make_id3_tags(frames={"TIT2": "AIFF Track"})
    audio = make_aiff_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.aiff")

    assert result["file_format"] == "aiff"
    assert result["tag_format_type"] == "id3"
    assert result["tag_title"] == "AIFF Track"
    assert result["bits_per_sample"] == 16


def test_wav_with_id3_chunk():
    """WAV with ID3 chunk reads tags and sets tags_present=True."""
    tags = make_id3_tags(frames={"TIT2": "WAV Track"})
    audio = make_wav_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.wav")

    assert result["file_format"] == "wav"
    assert result["tags_present"] is True
    assert result["tag_title"] == "WAV Track"


def test_wav_without_id3_chunk():
    """WAV without ID3 chunk: tags_present=False, tags_error=None, audio properties populated."""
    audio = make_wav_audio(tags=None)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.wav")

    assert result["file_format"] == "wav"
    assert result["tags_present"] is False
    assert result["tags_error"] is None
    assert result["duration_seconds"] == 300.0
    assert result["tag_title"] is None
    assert result["has_embedded_art"] is False


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_mutagen_file_returns_none():
    """mutagen.File() returning None → unrecognised format error dict."""
    with patch("mutagen.File", return_value=None):
        result = read_tags("unknown.xyz")

    assert result["tags_present"] is False
    assert result["tags_error"] == "unrecognised format"
    assert result["file_format"] == "unknown"
    assert result["duration_seconds"] is None


def test_mutagen_error_raised():
    """mutagen.MutagenError → error dict, no exception propagated."""
    with patch("mutagen.File", side_effect=mutagen.MutagenError("corrupt")):
        result = read_tags("corrupt.mp3")

    assert result["tags_present"] is False
    assert result["tags_error"] == "corrupt"
    assert result["duration_seconds"] is None


def test_all_tag_fields_absent():
    """MP3 with empty ID3 dict → all tag_* fields None, audio properties populated."""
    tags = make_id3_tags(frames={})
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("empty.mp3")

    assert result["tags_present"] is True
    assert result["tag_title"] is None
    assert result["tag_artist"] is None
    assert result["tag_bpm"] is None
    assert result["duration_seconds"] == 300.0


def test_tbpm_raw_string_preserved():
    """TBPM value '128.00' stored as-is, not converted to int."""
    tags = make_id3_tags(frames={"TBPM": "128.00"})
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_bpm"] == "128.00"


def test_tcon_raw_numeric_preserved():
    """TCON value '(17)' stored raw, not translated to genre name."""
    tags = make_id3_tags(frames={"TCON": "(17)"})
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_genre"] == "(17)"


def test_trck_raw_format_preserved():
    """TRCK value '3/12' stored raw."""
    tags = make_id3_tags(frames={"TRCK": "3/12"})
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_track_number"] == "3/12"


def test_txxx_catalognumber_present():
    """TXXX:CATALOGNUMBER frame populates tag_catalogue_no."""
    tags = make_id3_tags(frames={}, txxx_frames=[("CATALOGNUMBER", "CAT123")])
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_catalogue_no"] == "CAT123"


def test_txxx_catalogid_fallback():
    """TXXX:CATALOGID used when CATALOGNUMBER is absent."""
    tags = make_id3_tags(frames={}, txxx_frames=[("CATALOGID", "ID456")])
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_catalogue_no"] == "ID456"


def test_txxx_catalognumber_takes_precedence_over_catalogid():
    """CATALOGNUMBER takes precedence over CATALOGID when both are present."""
    tags = make_id3_tags(
        frames={},
        txxx_frames=[("CATALOGID", "WRONG"), ("CATALOGNUMBER", "CORRECT")],
    )
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_catalogue_no"] == "CORRECT"


def test_tkey_and_txxx_initialkey_both_stored():
    """TKEY and TXXX:INITIALKEY stored separately."""
    tags = make_id3_tags(
        frames={"TKEY": "Am"},
        txxx_frames=[("INITIALKEY", "11A")],
    )
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_key"] == "Am"
    assert result["tag_initial_key_txxx"] == "11A"


def test_apic_type3_sets_has_embedded_art():
    """APIC frame with type=3 sets has_embedded_art=True."""
    tags = make_id3_tags(frames={}, apic_frames=[3])
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["has_embedded_art"] is True


def test_apic_type4_only_does_not_set_has_embedded_art():
    """APIC frame with type=4 (back cover) does NOT set has_embedded_art=True."""
    tags = make_id3_tags(frames={}, apic_frames=[4])
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["has_embedded_art"] is False


def test_has_serato_tags_detection():
    """GEOB:Serato Analysis key in tags sets has_serato_tags=True."""
    tags = make_id3_tags(frames={}, extra_keys=["GEOB:Serato Analysis"])
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["has_serato_tags"] is True


def test_has_traktor_tags_detection():
    """PRIV:TRAKTOR4 key in tags sets has_traktor_tags=True."""
    tags = make_id3_tags(frames={}, extra_keys=["PRIV:TRAKTOR4"])
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["has_traktor_tags"] is True


def test_comm_empty_desc_selected():
    """COMM frame with empty .desc is preferred over a frame with a non-empty .desc."""
    tags = make_id3_tags(
        frames={},
        comm_frames=[("Purchase URL", "http://example.com"), ("", "The real comment")],
    )
    audio = make_mp3_audio(tags)

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["tag_comment"] == "The real comment"


# ---------------------------------------------------------------------------
# MP3-specific tests
# ---------------------------------------------------------------------------


def test_bitrate_mode_cbr():
    """bitrate_mode int value 1 is stored as string 'CBR'."""
    tags = make_id3_tags(frames={})
    audio = make_mp3_audio(tags)
    audio.info.bitrate_mode = 1  # BitrateMode.CBR

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["bitrate_mode"] == "CBR"


def test_sketchy_true():
    """is_sketchy=True stored as True."""
    tags = make_id3_tags(frames={})
    audio = make_mp3_audio(tags)
    audio.info.sketchy = True

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["is_sketchy"] is True


def test_encoder_info_empty_string_becomes_none():
    """encoder_info empty string '' is stored as None."""
    tags = make_id3_tags(frames={})
    audio = make_mp3_audio(tags)
    audio.info.encoder_info = ""

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["encoder_info"] is None


def test_encoder_info_non_empty_stored():
    """encoder_info non-empty string is stored as-is."""
    tags = make_id3_tags(frames={})
    audio = make_mp3_audio(tags)
    audio.info.encoder_info = "LAME3.100"

    with patch("mutagen.File", return_value=audio):
        result = read_tags("test.mp3")

    assert result["encoder_info"] == "LAME3.100"


# ---------------------------------------------------------------------------
# Top-level fallback test
# ---------------------------------------------------------------------------


def test_unexpected_exception_returns_dict():
    """An unexpected exception returns a dict with tags_error set, does not propagate."""
    with patch("mutagen.File", side_effect=ValueError("totally unexpected")):
        result = read_tags("weird.mp3")

    assert isinstance(result, dict)
    assert result["tags_error"] == "totally unexpected"
    assert result["tags_present"] is False


# ---------------------------------------------------------------------------
# Output schema completeness test
# ---------------------------------------------------------------------------


def test_output_dict_has_all_required_keys():
    """read_tags always returns a dict with every required output key."""
    expected_keys = {
        "file_path",
        "file_format",
        "duration_seconds",
        "bitrate_bps",
        "bitrate_mode",
        "sample_rate_hz",
        "channels",
        "bits_per_sample",
        "encoder_info",
        "is_sketchy",
        "tag_title",
        "tag_artist",
        "tag_album_artist",
        "tag_album",
        "tag_label",
        "tag_catalogue_no",
        "tag_genre",
        "tag_comment",
        "tag_isrc",
        "tag_copyright",
        "tag_year_id3v24",
        "tag_year_id3v23",
        "tag_date_released",
        "tag_date_original",
        "tag_date_vorbis",
        "tag_date_mp4",
        "tag_track_number",
        "tag_disc_number",
        "tag_bpm",
        "tag_key",
        "tag_energy",
        "tag_initial_key_txxx",
        "has_embedded_art",
        "has_serato_tags",
        "has_traktor_tags",
        "has_rekordbox_tags",
        "tag_id3_version",
        "tag_format_type",
        "tags_error",
        "tags_present",
    }
    with patch("mutagen.File", return_value=None):
        result = read_tags("test.mp3")

    assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"


def test_file_path_always_set():
    """file_path in returned dict always reflects the input path."""
    with patch("mutagen.File", return_value=None):
        result = read_tags("/some/path/track.mp3")

    assert result["file_path"] == "/some/path/track.mp3"


def test_pathlib_path_accepted():
    """read_tags accepts a pathlib.Path and converts it correctly."""
    import os
    from pathlib import Path

    p = Path("/some/path/track.mp3")
    with patch("mutagen.File", return_value=None):
        result = read_tags(p)

    assert result["file_path"] == os.fspath(p)
