"""
test_pipeline_merge.py — Unit tests for _build_db_row() and resolved_* fields.

All tests use fixed dicts as inputs — no importers called, no filesystem reads
beyond confirming the fixture exists.
"""

import json

from backend.importer.pipeline import _TRACKS_COLUMNS, _build_db_row, _year_from

# ---------------------------------------------------------------------------
# Helpers — minimal valid importer dicts
# ---------------------------------------------------------------------------

FILE_PATH = "/music/track.mp3"
FILE_HASH = "abc123"
FILE_SIZE = 1234567
FILE_MTIME = "1713456789.0"


def _tags(**overrides) -> dict:
    base = {
        "file_format": "MP3",
        "duration_seconds": 300.0,
        "bitrate_bps": 128000,
        "bitrate_mode": "CBR",
        "sample_rate_hz": 44100,
        "channels": 2,
        "bits_per_sample": None,
        "encoder_info": None,
        "is_sketchy": False,
        "tag_title": "Test Title",
        "tag_artist": "Test Artist",
        "tag_album_artist": None,
        "tag_album": "Test Album",
        "tag_label": "Test Label",
        "tag_catalogue_no": None,
        "tag_genre": "House",
        "tag_comment": None,
        "tag_isrc": None,
        "tag_copyright": None,
        "tag_year_id3v24": "2003",
        "tag_year_id3v23": None,
        "tag_date_released": None,
        "tag_date_original": None,
        "tag_date_vorbis": None,
        "tag_date_mp4": None,
        "tag_track_number": None,
        "tag_disc_number": None,
        "tag_bpm": "128.0",
        "tag_key": "Am",
        "tag_energy": None,
        "tag_initial_key_txxx": None,
        "has_embedded_art": False,
        "has_serato_tags": False,
        "has_traktor_tags": False,
        "has_rekordbox_tags": False,
        "tag_id3_version": "2.3",
        "tag_format_type": "id3",
        "tags_present": True,
        "tags_error": None,
    }
    base.update(overrides)
    return base


def _acoustid(**overrides) -> dict:
    base = {
        "acoustid_id": "aud-uuid",
        "acoustid_score": 0.95,
        "acoustid_match": True,
        "mb_recording_id": "rec-uuid",
        "mb_release_id": "rel-uuid",
        "mb_artist_id": "art-uuid",
        "mb_release_group_id": "rg-uuid",
        "mb_release_group_type": "Single",
        "title": "MB Title",
        "artist": "MB Artist",
        "artist_sort_name": "Artist, MB",
        "year": 2005,
        "mb_duration_s": 300,
        "isrc": "GBABC0512345",
        "mb_release_title": "MB Album",
        "release_status": "Official",
        "release_country": "DE",
        "label": "MB Label",
        "catalogue_number": "MB-001",
        "mb_has_front_art": True,
        "genres": ["techno"],
        "tags": [],
        "lookup_error": None,
    }
    base.update(overrides)
    return base


def _discogs(**overrides) -> dict:
    base = {
        "discogs_release_id": 12345,
        "discogs_master_id": None,
        "discogs_confidence": 4.5,
        "discogs_search_strategy": "artist+title",
        "discogs_url": "https://www.discogs.com/release/12345",
        "discogs_title": "Discogs Title",
        "discogs_year": 2004,
        "discogs_country": "Germany",
        "discogs_released": "2004-03-01",
        "discogs_released_formatted": "March 2004",
        "discogs_status": "Accepted",
        "discogs_data_quality": "Correct",
        "discogs_notes": None,
        "discogs_artists_sort": "Artist, Discogs",
        "discogs_num_for_sale": 10,
        "discogs_lowest_price": 5.0,
        "discogs_label_id": 999,
        "discogs_label": "Discogs Label",
        "discogs_catno": "DL-001",
        "discogs_label_entity_type": None,
        "discogs_artists": json.dumps([{"name": "Discogs Artist"}]),
        "discogs_genres": json.dumps(["Electronic"]),
        "discogs_styles": json.dumps(["Techno", "Deep House"]),
        "discogs_format_names": json.dumps(["Vinyl"]),
        "discogs_format_descs": json.dumps(['12"']),
        "discogs_producers": None,
        "discogs_remixers": None,
        "discogs_extraartists_raw": None,
        "discogs_labels_raw": None,
        "discogs_tracklist": None,
        "discogs_barcodes": None,
        "discogs_matrix_numbers": None,
        "discogs_have": 100,
        "discogs_want": 50,
        "discogs_rating_avg": 4.2,
        "discogs_rating_count": 20,
        "discogs_master_year": 2002,
        "discogs_master_most_recent_id": None,
        "discogs_master_url": None,
        "discogs_lookup_timestamp": "2026-04-19T00:00:00+00:00",
        "discogs_error": None,
    }
    base.update(overrides)
    return base


def _itunes(**overrides) -> dict:
    base = {
        "itunes_track_id": 777,
        "itunes_artist_id": 888,
        "itunes_collection_id": 999,
        "itunes_confidence": 0.85,
        "itunes_track_name": "iTunes Title",
        "itunes_artist_name": "iTunes Artist",
        "itunes_collection_name": "iTunes Album",
        "itunes_release_date": "2000-06-15T00:00:00Z",
        "itunes_track_time_ms": 300000,
        "itunes_disc_count": 1,
        "itunes_disc_number": 1,
        "itunes_track_count": 10,
        "itunes_track_number": 3,
        "itunes_genre": "Electronic",
        "itunes_track_explicit": "notExplicit",
        "itunes_is_streamable": True,
        "itunes_artwork_url": "https://example.com/itunes_art.jpg",
        "itunes_track_url": None,
        "itunes_artist_url": None,
        "itunes_collection_url": None,
        "itunes_collection_artist_id": None,
        "itunes_collection_artist_name": None,
        "itunes_search_strategy": "artist+title",
        "itunes_country": "us",
        "itunes_lookup_timestamp": "2026-04-19T00:00:00+00:00",
        "itunes_error": None,
    }
    base.update(overrides)
    return base


def _caa(**overrides) -> dict:
    base = {
        "cover_art_url": "https://coverartarchive.org/release/rel-uuid/front-500",
        "cover_art_source": "release",
        "cover_art_lookup_timestamp": "2026-04-19T00:00:00+00:00",
        "cover_art_error": None,
    }
    base.update(overrides)
    return base


def _essentia(**overrides) -> dict:
    base = {
        "bpm": 132.0,
        "bpm_confidence": 3.8,
        "beat_ticks": [0.1, 0.6],
        "bpm_estimates": [132.0],
        "bpm_intervals": [0.5],
        "key": "C",
        "key_scale": "minor",
        "key_strength": 0.85,
        "tuning_frequency_hz": 440.0,
        "tuning_cents": 0.0,
        "integrated_loudness": -9.0,
        "loudness_range": 3.5,
        "dynamic_complexity": 4.2,
        "dynamic_complexity_loudness": -8.0,
        "spectral_centroid_hz": 2200.0,
        "sub_bass_ratio": 0.15,
        "high_freq_ratio": 0.08,
        "mfcc_mean": [1.0, 2.0],
        "mfcc_var": [0.1, 0.2],
        "bark_bands_mean": [0.5],
        "danceability": 3.2,
        "danceability_dfa": [3.0, 3.4],
        "onset_times": [0.0, 0.5],
        "onset_rate": 4.0,
        "pitch_frames": [440.0],
        "pitch_confidence_frames": [0.9],
        "genre_probabilities": [0.8, 0.2],
        "genre_top_labels": ["techno", "house"],
        "arousal": 0.7,
        "valence": 0.4,
        "mood_aggressive": 0.3,
        "mood_happy": 0.5,
        "mood_party": 0.9,
        "mood_relaxed": 0.2,
        "mood_sad": 0.1,
        "instrument_probabilities": [0.6],
        "instrument_top_labels": ["synthesizer"],
        "moodtheme_probabilities": [0.5],
        "moodtheme_top_labels": ["party"],
        "ml_danceability": 0.85,
        "voice_probability": 0.05,
        "voice_probability_musicnn": 0.04,
        "essentia_version": "2.1b6.dev926",
        "analysis_timestamp": "2026-04-19T00:00:00+00:00",
        "analysis_error": None,
    }
    base.update(overrides)
    return base


def _build(**overrides_by_source):
    return _build_db_row(
        file_path=FILE_PATH,
        file_hash=FILE_HASH,
        file_size_bytes=FILE_SIZE,
        file_modified_at=FILE_MTIME,
        tags=overrides_by_source.get("tags", _tags()),
        acoustid=overrides_by_source.get("acoustid", _acoustid()),
        discogs=overrides_by_source.get("discogs", _discogs()),
        itunes=overrides_by_source.get("itunes", _itunes()),
        caa=overrides_by_source.get("caa", _caa()),
        essentia=overrides_by_source.get("essentia", _essentia()),
    )


# ---------------------------------------------------------------------------
# Column completeness
# ---------------------------------------------------------------------------


def test_build_db_row_has_all_columns():
    """Every column in _TRACKS_COLUMNS must be present in the output."""
    row = _build()
    missing = [c for c in _TRACKS_COLUMNS if c not in row]
    assert not missing, f"Missing columns: {missing}"


def test_build_db_row_no_extra_columns():
    """The output must not contain columns absent from _TRACKS_COLUMNS."""
    row = _build()
    extra = [k for k in row if k not in _TRACKS_COLUMNS]
    assert not extra, f"Unexpected columns: {extra}"


# ---------------------------------------------------------------------------
# _year_from helper
# ---------------------------------------------------------------------------


def test_year_from_int():
    assert _year_from(2003) == 2003


def test_year_from_string_year():
    assert _year_from("2003") == 2003


def test_year_from_iso_date():
    assert _year_from("2003-01-15") == 2003


def test_year_from_iso_datetime():
    assert _year_from("2005-01-01T00:00:00Z") == 2005


def test_year_from_none():
    assert _year_from(None) is None


def test_year_from_invalid():
    assert _year_from("abcd") is None


# ---------------------------------------------------------------------------
# resolved_year — priority chain
# ---------------------------------------------------------------------------


def test_resolved_year_mb_wins():
    """MB year (from acoustid) wins over all other sources."""
    row = _build(
        acoustid=_acoustid(year=2005),
        discogs=_discogs(discogs_year=2004, discogs_master_year=2002),
        tags=_tags(tag_year_id3v24="2001"),
        itunes=_itunes(itunes_release_date="2000-06-15T00:00:00Z"),
    )
    assert row["resolved_year"] == 2005


def test_resolved_year_discogs_year_second():
    row = _build(
        acoustid=_acoustid(year=None),
        discogs=_discogs(discogs_year=2004, discogs_master_year=2002),
        tags=_tags(tag_year_id3v24="2001"),
        itunes=_itunes(itunes_release_date="2000-06-15T00:00:00Z"),
    )
    assert row["resolved_year"] == 2004


def test_resolved_year_discogs_master_third():
    row = _build(
        acoustid=_acoustid(year=None),
        discogs=_discogs(discogs_year=None, discogs_master_year=2002),
        tags=_tags(tag_year_id3v24="2001"),
        itunes=_itunes(itunes_release_date="2000-06-15T00:00:00Z"),
    )
    assert row["resolved_year"] == 2002


def test_resolved_year_tag_id3v24_fourth():
    row = _build(
        acoustid=_acoustid(year=None),
        discogs=_discogs(discogs_year=None, discogs_master_year=None),
        tags=_tags(tag_year_id3v24="2001", tag_year_id3v23=None),
        itunes=_itunes(itunes_release_date="2000-06-15T00:00:00Z"),
    )
    assert row["resolved_year"] == 2001


def test_resolved_year_itunes_last():
    row = _build(
        acoustid=_acoustid(year=None),
        discogs=_discogs(discogs_year=None, discogs_master_year=None),
        tags=_tags(tag_year_id3v24=None, tag_year_id3v23=None),
        itunes=_itunes(itunes_release_date="2000-06-15T00:00:00Z"),
    )
    assert row["resolved_year"] == 2000


def test_resolved_year_none_when_all_absent():
    row = _build(
        acoustid=_acoustid(year=None),
        discogs=_discogs(discogs_year=None, discogs_master_year=None),
        tags=_tags(tag_year_id3v24=None, tag_year_id3v23=None),
        itunes=_itunes(itunes_release_date=None),
    )
    assert row["resolved_year"] is None


# ---------------------------------------------------------------------------
# resolved_title — falls back to filename stem
# ---------------------------------------------------------------------------


def test_resolved_title_uses_mb_first():
    row = _build(acoustid=_acoustid(title="MB Title"), tags=_tags(tag_title="Tag Title"))
    assert row["resolved_title"] == "MB Title"


def test_resolved_title_falls_back_to_tag():
    row = _build(acoustid=_acoustid(title=None), tags=_tags(tag_title="Tag Title"))
    assert row["resolved_title"] == "Tag Title"


def test_resolved_title_falls_back_to_stem():
    row = _build(acoustid=_acoustid(title=None), tags=_tags(tag_title=None))
    assert row["resolved_title"] == "track"  # stem of /music/track.mp3


# ---------------------------------------------------------------------------
# resolved_key — essentia combined key wins
# ---------------------------------------------------------------------------


def test_resolved_key_uses_essentia():
    row = _build(essentia=_essentia(key="C", key_scale="minor"))
    assert row["resolved_key"] == "C minor"


def test_resolved_key_falls_back_to_tag_key():
    row = _build(
        essentia=_essentia(key=None, key_scale=None),
        tags=_tags(tag_key="Am", tag_initial_key_txxx=None),
    )
    assert row["resolved_key"] == "Am"


def test_resolved_key_falls_back_to_txxx():
    row = _build(
        essentia=_essentia(key=None, key_scale=None),
        tags=_tags(tag_key=None, tag_initial_key_txxx="5m"),
    )
    assert row["resolved_key"] == "5m"


# ---------------------------------------------------------------------------
# resolved_bpm — essentia wins; tag_bpm cast from string
# ---------------------------------------------------------------------------


def test_resolved_bpm_uses_essentia():
    row = _build(essentia=_essentia(bpm=132.0), tags=_tags(tag_bpm="128.0"))
    assert row["resolved_bpm"] == 132.0


def test_resolved_bpm_casts_tag_string():
    row = _build(essentia=_essentia(bpm=None), tags=_tags(tag_bpm="128.0"))
    assert row["resolved_bpm"] == 128.0


def test_resolved_bpm_handles_invalid_tag():
    row = _build(essentia=_essentia(bpm=None), tags=_tags(tag_bpm="not-a-number"))
    assert row["resolved_bpm"] is None


# ---------------------------------------------------------------------------
# resolved_artwork_url — iTunes wins over CAA
# ---------------------------------------------------------------------------


def test_resolved_artwork_itunes_wins():
    row = _build(
        itunes=_itunes(itunes_artwork_url="https://itunes.example/art.jpg"),
        caa=_caa(cover_art_url="https://caa.example/art.jpg"),
    )
    assert row["resolved_artwork_url"] == "https://itunes.example/art.jpg"


def test_resolved_artwork_falls_back_to_caa():
    row = _build(
        itunes=_itunes(itunes_artwork_url=None),
        caa=_caa(cover_art_url="https://caa.example/art.jpg"),
    )
    assert row["resolved_artwork_url"] == "https://caa.example/art.jpg"


# ---------------------------------------------------------------------------
# discogs_styles_search computed column
# ---------------------------------------------------------------------------


def test_discogs_styles_search_computed():
    import json

    row = _build(discogs=_discogs(discogs_styles=json.dumps(["Techno", "Deep House"])))
    assert row["discogs_styles_search"] == "Techno Deep House"


def test_discogs_styles_search_none_when_null():
    row = _build(discogs=_discogs(discogs_styles=None))
    assert row["discogs_styles_search"] is None


# ---------------------------------------------------------------------------
# es_genre_top_labels_search computed column
# ---------------------------------------------------------------------------


def test_es_genre_top_labels_search_computed():
    row = _build(essentia=_essentia(genre_top_labels=["techno", "house"]))
    assert row["es_genre_top_labels_search"] == "techno house"


def test_es_genre_top_labels_search_none_when_empty(tmp_path):
    row = _build(essentia=_essentia(genre_top_labels=None))
    assert row["es_genre_top_labels_search"] is None


# ---------------------------------------------------------------------------
# Empty importer dicts — pipeline must not crash
# ---------------------------------------------------------------------------


def test_empty_acoustid_does_not_crash():
    row = _build(acoustid={})
    assert row["mb_title"] is None
    assert row["resolved_title"] == "Test Title"  # falls back to tag


def test_empty_discogs_does_not_crash():
    row = _build(discogs={})
    assert row["discogs_label"] is None


def test_empty_essentia_does_not_crash():
    row = _build(essentia={})
    assert row["es_bpm"] is None
    # resolved_bpm should fall back to tag_bpm
    assert row["resolved_bpm"] == 128.0


def test_all_empty_importers_resolved_title_is_stem():
    row = _build(
        acoustid={},
        discogs={},
        itunes={},
        caa={},
        essentia={},
        tags=_tags(tag_title=None, tag_bpm=None, tag_year_id3v24=None, tag_year_id3v23=None),
    )
    assert row["resolved_title"] == "track"
    assert row["resolved_year"] is None
