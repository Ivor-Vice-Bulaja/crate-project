"""
pipeline.py — Import pipeline orchestrator for Crate.

Receives a single audio file path and a database connection, calls all six
importers in dependency order, merges their flat dicts via an explicit
column-mapping layer, computes resolved_* canonical fields, and writes a
single row to the tracks table.

Never raises to the caller — all exceptions are caught, logged, and a
partial result (or None) is returned.

Public API:
    import_track(file_path, db, config, progress_callback=None) -> dict | None
    import_tracks(paths, db, config, on_progress=None) -> None
"""

import contextlib
import hashlib
import json
import logging
import os
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime
from pathlib import Path

from backend.config import PipelineConfig
from backend.importer.acoustid import identify_track
from backend.importer.cover_art import fetch_cover_art
from backend.importer.discogs import fetch_discogs_metadata
from backend.importer.itunes import fetch_itunes
from backend.importer.tags import read_tags

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Essentia availability — checked once at import time
# ---------------------------------------------------------------------------


def _is_essentia_available() -> bool:
    """Return True if essentia is importable in the current environment."""
    try:
        import essentia.standard  # noqa: F401

        return True
    except ImportError:
        return False


_ESSENTIA_AVAILABLE: bool = _is_essentia_available()

if not _ESSENTIA_AVAILABLE:
    logger.info(
        "Essentia audio analysis disabled: essentia package not importable. "
        "Re-run from WSL2 with `uv sync --extra analysis` to enable."
    )

# ---------------------------------------------------------------------------
# Per-track logger adapter
# ---------------------------------------------------------------------------


class _TrackLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra['path']}] {msg}", kwargs


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------


def _hash_file(path: str, chunk_size: int = 65536) -> str:
    """Return MD5 hex digest of the file at path, reading in chunks."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _check_skip(path: str, db: sqlite3.Connection) -> bool:
    """
    Return True if the file is already imported and its content is unchanged.

    Strategy: check mtime first (O(1), no read). Only hash the file if mtime
    changed — avoids hashing 10,000 unchanged tracks in a batch.
    """
    current_mtime = str(os.stat(path).st_mtime)
    row = db.execute(
        "SELECT file_modified_at, file_hash FROM tracks WHERE file_path = ?",
        (path,),
    ).fetchone()
    if row is None:
        return False  # new file — never imported
    if row["file_modified_at"] == current_mtime:
        return True  # mtime unchanged — fast path skip
    # mtime changed — verify content before deciding to re-import
    current_hash = _hash_file(path)
    if current_hash == row["file_hash"]:
        return True  # touch/copy artifact — content unchanged
    return False  # content changed — re-import


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _year_from(value) -> int | None:
    """Extract a 4-digit year integer from a string, int, or None."""
    if value is None:
        return None
    s = str(value)[:4]
    return int(s) if s.isdigit() else None


def _collect(future, name: str, timeout: int) -> dict:
    """Retrieve a future result; return {} on timeout or exception."""
    if future is None:
        return {}
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        logger.warning("%s timed out after %ds", name, timeout)
        return {}
    except Exception as exc:
        logger.error("%s raised unexpectedly: %s", name, exc)
        return {}


# ---------------------------------------------------------------------------
# _TRACKS_COLUMNS — must match the database schema exactly (excluding 'id')
# ---------------------------------------------------------------------------

_TRACKS_COLUMNS = [
    "file_path",
    "file_hash",
    "file_size_bytes",
    "file_modified_at",
    "tag_file_format",
    "tag_duration_seconds",
    "tag_bitrate_bps",
    "tag_bitrate_mode",
    "tag_sample_rate_hz",
    "tag_channels",
    "tag_bits_per_sample",
    "tag_encoder_info",
    "tag_is_sketchy",
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
    "tag_has_embedded_art",
    "tag_has_serato_tags",
    "tag_has_traktor_tags",
    "tag_has_rekordbox_tags",
    "tag_id3_version",
    "tag_format_type",
    "tag_tags_present",
    "tag_error",
    "acoustid_id",
    "acoustid_score",
    "acoustid_match",
    "mb_recording_id",
    "mb_release_id",
    "mb_artist_id",
    "mb_release_group_id",
    "mb_release_group_type",
    "mb_title",
    "mb_artist",
    "mb_artist_sort_name",
    "mb_year",
    "mb_duration_s",
    "mb_isrc",
    "mb_release_title",
    "mb_release_status",
    "mb_release_country",
    "mb_label",
    "mb_catalogue_number",
    "mb_has_front_art",
    "mb_genres",
    "mb_tags",
    "mb_lookup_error",
    "discogs_release_id",
    "discogs_master_id",
    "discogs_confidence",
    "discogs_search_strategy",
    "discogs_url",
    "discogs_title",
    "discogs_year",
    "discogs_country",
    "discogs_released",
    "discogs_released_formatted",
    "discogs_status",
    "discogs_data_quality",
    "discogs_notes",
    "discogs_artists_sort",
    "discogs_num_for_sale",
    "discogs_lowest_price",
    "discogs_label_id",
    "discogs_label",
    "discogs_catno",
    "discogs_label_entity_type",
    "discogs_artists",
    "discogs_genres",
    "discogs_styles",
    "discogs_styles_search",
    "discogs_format_names",
    "discogs_format_descs",
    "discogs_producers",
    "discogs_remixers",
    "discogs_extraartists_raw",
    "discogs_labels_raw",
    "discogs_tracklist",
    "discogs_barcodes",
    "discogs_matrix_numbers",
    "discogs_have",
    "discogs_want",
    "discogs_rating_avg",
    "discogs_rating_count",
    "discogs_master_year",
    "discogs_master_most_recent_id",
    "discogs_master_url",
    "discogs_lookup_timestamp",
    "discogs_error",
    "itunes_track_id",
    "itunes_artist_id",
    "itunes_collection_id",
    "itunes_confidence",
    "itunes_track_name",
    "itunes_artist_name",
    "itunes_collection_name",
    "itunes_release_date",
    "itunes_track_time_ms",
    "itunes_disc_count",
    "itunes_disc_number",
    "itunes_track_count",
    "itunes_track_number",
    "itunes_genre",
    "itunes_track_explicit",
    "itunes_is_streamable",
    "itunes_artwork_url",
    "itunes_track_url",
    "itunes_artist_url",
    "itunes_collection_url",
    "itunes_collection_artist_id",
    "itunes_collection_artist_name",
    "itunes_search_strategy",
    "itunes_country",
    "itunes_lookup_timestamp",
    "itunes_error",
    "caa_url",
    "caa_source",
    "caa_lookup_timestamp",
    "caa_error",
    "es_bpm",
    "es_bpm_confidence",
    "es_beat_ticks",
    "es_bpm_estimates",
    "es_bpm_intervals",
    "es_key",
    "es_key_scale",
    "es_key_strength",
    "es_tuning_frequency_hz",
    "es_tuning_cents",
    "es_integrated_loudness",
    "es_loudness_range",
    "es_dynamic_complexity",
    "es_dynamic_complexity_loudness",
    "es_spectral_centroid_hz",
    "es_sub_bass_ratio",
    "es_high_freq_ratio",
    "es_mfcc_mean",
    "es_mfcc_var",
    "es_bark_bands_mean",
    "es_danceability",
    "es_danceability_dfa",
    "es_onset_times",
    "es_onset_rate",
    "es_pitch_frames",
    "es_pitch_confidence_frames",
    "es_genre_probabilities",
    "es_genre_top_labels",
    "es_genre_top_labels_search",
    "es_arousal",
    "es_valence",
    "es_mood_aggressive",
    "es_mood_happy",
    "es_mood_party",
    "es_mood_relaxed",
    "es_mood_sad",
    "es_instrument_probabilities",
    "es_instrument_top_labels",
    "es_moodtheme_probabilities",
    "es_moodtheme_top_labels",
    "es_ml_danceability",
    "es_voice_probability",
    "es_voice_probability_musicnn",
    "es_version",
    "es_analysis_timestamp",
    "es_analysis_error",
    "resolved_title",
    "resolved_artist",
    "resolved_bpm",
    "resolved_key",
    "resolved_label",
    "resolved_year",
    "resolved_artwork_url",
    "last_played_at",
    "play_count",
    "imported_at",
    "tags_imported_at",
    "acoustid_imported_at",
    "discogs_imported_at",
    "itunes_imported_at",
    "caa_imported_at",
    "essentia_imported_at",
]

_cols_str = ", ".join(_TRACKS_COLUMNS)
_vals_str = ", ".join(f":{c}" for c in _TRACKS_COLUMNS)
_update_str = ", ".join(f"{c} = excluded.{c}" for c in _TRACKS_COLUMNS if c != "file_path")

_INSERT_SQL = f"""
INSERT INTO tracks ({_cols_str})
VALUES ({_vals_str})
ON CONFLICT(file_path) DO UPDATE SET
    {_update_str}
"""

# ---------------------------------------------------------------------------
# _build_db_row — explicit column mapping + resolved field computation
# ---------------------------------------------------------------------------


def _build_db_row(
    file_path: str,
    file_hash: str,
    file_size_bytes: int,
    file_modified_at: str,
    tags: dict,
    acoustid: dict,
    discogs: dict,
    itunes: dict,
    caa: dict,
    essentia: dict,
) -> dict:
    """
    Build a dict keyed exactly to _TRACKS_COLUMNS by mapping each importer's
    returned keys to their DB column names and computing resolved_* fields.
    """
    now = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    # Resolved fields
    # ------------------------------------------------------------------

    resolved_title = next(
        (v for v in [acoustid.get("title"), tags.get("tag_title")] if v),
        Path(file_path).stem,
    )

    resolved_artist = next(
        (
            v
            for v in [
                acoustid.get("artist"),
                tags.get("tag_artist"),
                discogs.get("discogs_artists_sort"),
            ]
            if v
        ),
        None,
    )

    _tag_bpm_raw = tags.get("tag_bpm")
    _tag_bpm = None
    if _tag_bpm_raw:
        with contextlib.suppress(ValueError, TypeError):
            _tag_bpm = float(_tag_bpm_raw)

    resolved_bpm = next(
        (v for v in [essentia.get("bpm"), _tag_bpm] if v),
        None,
    )

    _es_key = essentia.get("key")
    _es_key_scale = essentia.get("key_scale")
    _es_key_combined = f"{_es_key} {_es_key_scale}" if _es_key and _es_key_scale else None

    resolved_key = next(
        (
            v
            for v in [
                _es_key_combined,
                tags.get("tag_key"),
                tags.get("tag_initial_key_txxx"),
            ]
            if v
        ),
        None,
    )

    resolved_label = next(
        (
            v
            for v in [
                acoustid.get("label"),
                discogs.get("discogs_label"),
                tags.get("tag_label"),
            ]
            if v
        ),
        None,
    )

    resolved_year = next(
        (
            v
            for v in [
                _year_from(acoustid.get("year")),
                _year_from(discogs.get("discogs_year")),
                _year_from(discogs.get("discogs_master_year")),
                _year_from(tags.get("tag_year_id3v24")),
                _year_from(tags.get("tag_year_id3v23")),
                _year_from(itunes.get("itunes_release_date")),
            ]
            if v
        ),
        None,
    )

    resolved_artwork_url = next(
        (
            v
            for v in [
                itunes.get("itunes_artwork_url"),
                caa.get("cover_art_url"),
            ]
            if v
        ),
        None,
    )

    # ------------------------------------------------------------------
    # Computed columns not returned directly by any importer
    # ------------------------------------------------------------------

    _discogs_styles_raw = discogs.get("discogs_styles")
    if _discogs_styles_raw:
        try:
            _styles_list = json.loads(_discogs_styles_raw)
            discogs_styles_search = " ".join(_styles_list) if _styles_list else None
        except (json.JSONDecodeError, TypeError):
            discogs_styles_search = None
    else:
        discogs_styles_search = None

    _genre_top_labels = essentia.get("genre_top_labels")
    es_genre_top_labels_search = " ".join(_genre_top_labels) if _genre_top_labels else None

    # ------------------------------------------------------------------
    # Per-importer timestamps
    # ------------------------------------------------------------------

    tags_imported_at = now if tags else None
    acoustid_imported_at = now if acoustid.get("acoustid_match") is not None else None
    discogs_imported_at = now if discogs.get("discogs_lookup_timestamp") else None
    itunes_imported_at = now if itunes.get("itunes_lookup_timestamp") else None
    caa_imported_at = now if caa.get("caa_lookup_timestamp") else None
    essentia_imported_at = now if essentia.get("analysis_timestamp") else None

    # ------------------------------------------------------------------
    # Assemble row — every key maps to a _TRACKS_COLUMNS entry
    # ------------------------------------------------------------------

    row = {
        # File metadata
        "file_path": file_path,
        "file_hash": file_hash,
        "file_size_bytes": file_size_bytes,
        "file_modified_at": file_modified_at,
        # Tags (rename where key differs from column name)
        "tag_file_format": tags.get("file_format"),
        "tag_duration_seconds": tags.get("duration_seconds"),
        "tag_bitrate_bps": tags.get("bitrate_bps"),
        "tag_bitrate_mode": tags.get("bitrate_mode"),
        "tag_sample_rate_hz": tags.get("sample_rate_hz"),
        "tag_channels": tags.get("channels"),
        "tag_bits_per_sample": tags.get("bits_per_sample"),
        "tag_encoder_info": tags.get("encoder_info"),
        "tag_is_sketchy": tags.get("is_sketchy"),
        "tag_title": tags.get("tag_title"),
        "tag_artist": tags.get("tag_artist"),
        "tag_album_artist": tags.get("tag_album_artist"),
        "tag_album": tags.get("tag_album"),
        "tag_label": tags.get("tag_label"),
        "tag_catalogue_no": tags.get("tag_catalogue_no"),
        "tag_genre": tags.get("tag_genre"),
        "tag_comment": tags.get("tag_comment"),
        "tag_isrc": tags.get("tag_isrc"),
        "tag_copyright": tags.get("tag_copyright"),
        "tag_year_id3v24": tags.get("tag_year_id3v24"),
        "tag_year_id3v23": tags.get("tag_year_id3v23"),
        "tag_date_released": tags.get("tag_date_released"),
        "tag_date_original": tags.get("tag_date_original"),
        "tag_date_vorbis": tags.get("tag_date_vorbis"),
        "tag_date_mp4": tags.get("tag_date_mp4"),
        "tag_track_number": tags.get("tag_track_number"),
        "tag_disc_number": tags.get("tag_disc_number"),
        "tag_bpm": tags.get("tag_bpm"),
        "tag_key": tags.get("tag_key"),
        "tag_energy": tags.get("tag_energy"),
        "tag_initial_key_txxx": tags.get("tag_initial_key_txxx"),
        "tag_has_embedded_art": tags.get("has_embedded_art"),
        "tag_has_serato_tags": tags.get("has_serato_tags"),
        "tag_has_traktor_tags": tags.get("has_traktor_tags"),
        "tag_has_rekordbox_tags": tags.get("has_rekordbox_tags"),
        "tag_id3_version": tags.get("tag_id3_version"),
        "tag_format_type": tags.get("tag_format_type"),
        "tag_tags_present": tags.get("tags_present"),
        "tag_error": tags.get("tags_error"),
        # AcoustID / MusicBrainz (rename non-matching keys)
        "acoustid_id": acoustid.get("acoustid_id"),
        "acoustid_score": acoustid.get("acoustid_score"),
        "acoustid_match": acoustid.get("acoustid_match"),
        "mb_recording_id": acoustid.get("mb_recording_id"),
        "mb_release_id": acoustid.get("mb_release_id"),
        "mb_artist_id": acoustid.get("mb_artist_id"),
        "mb_release_group_id": acoustid.get("mb_release_group_id"),
        "mb_release_group_type": acoustid.get("mb_release_group_type"),
        "mb_title": acoustid.get("title"),
        "mb_artist": acoustid.get("artist"),
        "mb_artist_sort_name": acoustid.get("artist_sort_name"),
        "mb_year": acoustid.get("year"),
        "mb_duration_s": acoustid.get("mb_duration_s"),
        "mb_isrc": acoustid.get("isrc"),
        "mb_release_title": acoustid.get("mb_release_title"),
        "mb_release_status": acoustid.get("release_status"),
        "mb_release_country": acoustid.get("release_country"),
        "mb_label": acoustid.get("label"),
        "mb_catalogue_number": acoustid.get("catalogue_number"),
        "mb_has_front_art": acoustid.get("mb_has_front_art"),
        "mb_genres": json.dumps(acoustid.get("genres") or []),
        "mb_tags": json.dumps(acoustid.get("tags") or []),
        "mb_lookup_error": acoustid.get("lookup_error"),
        # Discogs — keys already prefixed discogs_* (direct pass-through)
        "discogs_release_id": discogs.get("discogs_release_id"),
        "discogs_master_id": discogs.get("discogs_master_id"),
        "discogs_confidence": discogs.get("discogs_confidence"),
        "discogs_search_strategy": discogs.get("discogs_search_strategy"),
        "discogs_url": discogs.get("discogs_url"),
        "discogs_title": discogs.get("discogs_title"),
        "discogs_year": discogs.get("discogs_year"),
        "discogs_country": discogs.get("discogs_country"),
        "discogs_released": discogs.get("discogs_released"),
        "discogs_released_formatted": discogs.get("discogs_released_formatted"),
        "discogs_status": discogs.get("discogs_status"),
        "discogs_data_quality": discogs.get("discogs_data_quality"),
        "discogs_notes": discogs.get("discogs_notes"),
        "discogs_artists_sort": discogs.get("discogs_artists_sort"),
        "discogs_num_for_sale": discogs.get("discogs_num_for_sale"),
        "discogs_lowest_price": discogs.get("discogs_lowest_price"),
        "discogs_label_id": discogs.get("discogs_label_id"),
        "discogs_label": discogs.get("discogs_label"),
        "discogs_catno": discogs.get("discogs_catno"),
        "discogs_label_entity_type": discogs.get("discogs_label_entity_type"),
        "discogs_artists": discogs.get("discogs_artists"),
        "discogs_genres": discogs.get("discogs_genres"),
        "discogs_styles": discogs.get("discogs_styles"),
        "discogs_styles_search": discogs_styles_search,
        "discogs_format_names": discogs.get("discogs_format_names"),
        "discogs_format_descs": discogs.get("discogs_format_descs"),
        "discogs_producers": discogs.get("discogs_producers"),
        "discogs_remixers": discogs.get("discogs_remixers"),
        "discogs_extraartists_raw": discogs.get("discogs_extraartists_raw"),
        "discogs_labels_raw": discogs.get("discogs_labels_raw"),
        "discogs_tracklist": discogs.get("discogs_tracklist"),
        "discogs_barcodes": discogs.get("discogs_barcodes"),
        "discogs_matrix_numbers": discogs.get("discogs_matrix_numbers"),
        "discogs_have": discogs.get("discogs_have"),
        "discogs_want": discogs.get("discogs_want"),
        "discogs_rating_avg": discogs.get("discogs_rating_avg"),
        "discogs_rating_count": discogs.get("discogs_rating_count"),
        "discogs_master_year": discogs.get("discogs_master_year"),
        "discogs_master_most_recent_id": discogs.get("discogs_master_most_recent_id"),
        "discogs_master_url": discogs.get("discogs_master_url"),
        "discogs_lookup_timestamp": discogs.get("discogs_lookup_timestamp"),
        "discogs_error": discogs.get("discogs_error"),
        # iTunes — keys already prefixed itunes_* (direct pass-through)
        "itunes_track_id": itunes.get("itunes_track_id"),
        "itunes_artist_id": itunes.get("itunes_artist_id"),
        "itunes_collection_id": itunes.get("itunes_collection_id"),
        "itunes_confidence": itunes.get("itunes_confidence"),
        "itunes_track_name": itunes.get("itunes_track_name"),
        "itunes_artist_name": itunes.get("itunes_artist_name"),
        "itunes_collection_name": itunes.get("itunes_collection_name"),
        "itunes_release_date": itunes.get("itunes_release_date"),
        "itunes_track_time_ms": itunes.get("itunes_track_time_ms"),
        "itunes_disc_count": itunes.get("itunes_disc_count"),
        "itunes_disc_number": itunes.get("itunes_disc_number"),
        "itunes_track_count": itunes.get("itunes_track_count"),
        "itunes_track_number": itunes.get("itunes_track_number"),
        "itunes_genre": itunes.get("itunes_genre"),
        "itunes_track_explicit": itunes.get("itunes_track_explicit"),
        "itunes_is_streamable": itunes.get("itunes_is_streamable"),
        "itunes_artwork_url": itunes.get("itunes_artwork_url"),
        "itunes_track_url": itunes.get("itunes_track_url"),
        "itunes_artist_url": itunes.get("itunes_artist_url"),
        "itunes_collection_url": itunes.get("itunes_collection_url"),
        "itunes_collection_artist_id": itunes.get("itunes_collection_artist_id"),
        "itunes_collection_artist_name": itunes.get("itunes_collection_artist_name"),
        "itunes_search_strategy": itunes.get("itunes_search_strategy"),
        "itunes_country": itunes.get("itunes_country"),
        "itunes_lookup_timestamp": itunes.get("itunes_lookup_timestamp"),
        "itunes_error": itunes.get("itunes_error"),
        # Cover Art Archive (rename cover_art_* → caa_*)
        "caa_url": caa.get("cover_art_url"),
        "caa_source": caa.get("cover_art_source"),
        "caa_lookup_timestamp": caa.get("cover_art_lookup_timestamp"),
        "caa_error": caa.get("cover_art_error"),
        # Essentia (rename to es_*)
        "es_bpm": essentia.get("bpm"),
        "es_bpm_confidence": essentia.get("bpm_confidence"),
        "es_beat_ticks": json.dumps(essentia.get("beat_ticks") or []),
        "es_bpm_estimates": json.dumps(essentia.get("bpm_estimates") or []),
        "es_bpm_intervals": json.dumps(essentia.get("bpm_intervals") or []),
        "es_key": essentia.get("key"),
        "es_key_scale": essentia.get("key_scale"),
        "es_key_strength": essentia.get("key_strength"),
        "es_tuning_frequency_hz": essentia.get("tuning_frequency_hz"),
        "es_tuning_cents": essentia.get("tuning_cents"),
        "es_integrated_loudness": essentia.get("integrated_loudness"),
        "es_loudness_range": essentia.get("loudness_range"),
        "es_dynamic_complexity": essentia.get("dynamic_complexity"),
        "es_dynamic_complexity_loudness": essentia.get("dynamic_complexity_loudness"),
        "es_spectral_centroid_hz": essentia.get("spectral_centroid_hz"),
        "es_sub_bass_ratio": essentia.get("sub_bass_ratio"),
        "es_high_freq_ratio": essentia.get("high_freq_ratio"),
        "es_mfcc_mean": json.dumps(essentia.get("mfcc_mean") or []),
        "es_mfcc_var": json.dumps(essentia.get("mfcc_var") or []),
        "es_bark_bands_mean": json.dumps(essentia.get("bark_bands_mean") or []),
        "es_danceability": essentia.get("danceability"),
        "es_danceability_dfa": json.dumps(essentia.get("danceability_dfa") or []),
        "es_onset_times": json.dumps(essentia.get("onset_times") or []),
        "es_onset_rate": essentia.get("onset_rate"),
        "es_pitch_frames": json.dumps(essentia.get("pitch_frames") or []),
        "es_pitch_confidence_frames": json.dumps(essentia.get("pitch_confidence_frames") or []),
        "es_genre_probabilities": json.dumps(essentia.get("genre_probabilities") or []),
        "es_genre_top_labels": json.dumps(essentia.get("genre_top_labels") or []),
        "es_genre_top_labels_search": es_genre_top_labels_search,
        "es_arousal": essentia.get("arousal"),
        "es_valence": essentia.get("valence"),
        "es_mood_aggressive": essentia.get("mood_aggressive"),
        "es_mood_happy": essentia.get("mood_happy"),
        "es_mood_party": essentia.get("mood_party"),
        "es_mood_relaxed": essentia.get("mood_relaxed"),
        "es_mood_sad": essentia.get("mood_sad"),
        "es_instrument_probabilities": json.dumps(essentia.get("instrument_probabilities") or []),
        "es_instrument_top_labels": json.dumps(essentia.get("instrument_top_labels") or []),
        "es_moodtheme_probabilities": json.dumps(essentia.get("moodtheme_probabilities") or []),
        "es_moodtheme_top_labels": json.dumps(essentia.get("moodtheme_top_labels") or []),
        "es_ml_danceability": essentia.get("ml_danceability"),
        "es_voice_probability": essentia.get("voice_probability"),
        "es_voice_probability_musicnn": essentia.get("voice_probability_musicnn"),
        "es_version": essentia.get("essentia_version"),
        "es_analysis_timestamp": essentia.get("analysis_timestamp"),
        "es_analysis_error": essentia.get("analysis_error"),
        # Resolved canonical fields
        "resolved_title": resolved_title,
        "resolved_artist": resolved_artist,
        "resolved_bpm": resolved_bpm,
        "resolved_key": resolved_key,
        "resolved_label": resolved_label,
        "resolved_year": resolved_year,
        "resolved_artwork_url": resolved_artwork_url,
        # Usage tracking — never set on import
        "last_played_at": None,
        "play_count": None,
        # Import timestamps
        "imported_at": now,
        "tags_imported_at": tags_imported_at,
        "acoustid_imported_at": acoustid_imported_at,
        "discogs_imported_at": discogs_imported_at,
        "itunes_imported_at": itunes_imported_at,
        "caa_imported_at": caa_imported_at,
        "essentia_imported_at": essentia_imported_at,
    }

    return row


# ---------------------------------------------------------------------------
# import_track — single-track pipeline
# ---------------------------------------------------------------------------


def import_track(
    file_path: str | Path,
    db: sqlite3.Connection,
    config: PipelineConfig,
    progress_callback: Callable[[str], None] | None = None,
) -> dict | None:
    """
    Import a single audio file into the tracks table.

    Returns the merged dict written to the DB, or None on hash-hit skip or
    unrecoverable error. Never raises.
    """
    path = os.fspath(file_path)
    tlog = _TrackLogger(logger, {"path": path})

    try:
        # ------------------------------------------------------------------
        # Step 1 — change detection
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback("checking")

        if _check_skip(path, db):
            tlog.debug("Skipping unchanged file")
            if progress_callback:
                progress_callback("skipped")
            return None

        # ------------------------------------------------------------------
        # Step 2 — hash + stat for INSERT (we need both regardless)
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback("hashing")

        file_hash = _hash_file(path)
        stat = os.stat(path)
        file_size_bytes = stat.st_size
        file_modified_at = str(stat.st_mtime)

        # ------------------------------------------------------------------
        # Step 3 — read tags (synchronous, instant)
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback("reading tags")

        tags = read_tags(path)
        if tags.get("tags_error"):
            tlog.warning("read_tags error: %s", tags.get("tags_error"))

        # ------------------------------------------------------------------
        # Step 4 — concurrent importers: AcoustID + Essentia
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback("running importers")

        fut_essentia = None
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            fut_acoustid = executor.submit(identify_track, path, config.acoustid)
            if _ESSENTIA_AVAILABLE:
                from backend.importer.essentia_analysis import analyse_track

                fut_essentia = executor.submit(analyse_track, path, config.essentia)
        # Executor has shut down — all threads complete before this line.

        acoustid_result = _collect(fut_acoustid, "acoustid", timeout=90)
        essentia_result = _collect(fut_essentia, "essentia", timeout=300)

        if acoustid_result.get("lookup_error"):
            tlog.warning("acoustid returned error: %s", acoustid_result.get("lookup_error"))

        # ------------------------------------------------------------------
        # Step 5 — Discogs + iTunes (both depend on tags + acoustid result)
        # ------------------------------------------------------------------
        mb_artist = acoustid_result.get("artist")
        mb_title = acoustid_result.get("title")
        mb_label = acoustid_result.get("label")
        mb_catno = acoustid_result.get("catalogue_number")
        mb_year = acoustid_result.get("year")

        discogs_result = fetch_discogs_metadata(
            artist=tags.get("tag_artist") or mb_artist,
            title=tags.get("tag_title") or mb_title,
            label=tags.get("tag_label") or mb_label,
            catno=tags.get("tag_catalogue_no") or mb_catno,
            barcode=None,
            year=mb_year or _year_from(tags.get("tag_year_id3v24")),
            client=config.discogs_client,
            config=config.discogs,
        )

        if discogs_result.get("discogs_error"):
            tlog.warning("discogs returned error: %s", discogs_result.get("discogs_error"))

        itunes_result = fetch_itunes(
            artist=tags.get("tag_artist") or mb_artist or "",
            title=tags.get("tag_title") or mb_title or "",
            duration_seconds=tags.get("duration_seconds"),
            config=config.itunes,
        )
        if itunes_result.get("itunes_error"):
            tlog.warning("itunes returned error: %s", itunes_result.get("itunes_error"))

        # ------------------------------------------------------------------
        # Step 6 — Cover Art (depends on acoustid result)
        # ------------------------------------------------------------------
        caa_result = fetch_cover_art(
            release_mbid=acoustid_result.get("mb_release_id"),
            release_group_mbid=acoustid_result.get("mb_release_group_id"),
            config=config.cover_art,
            mb_has_front_art=acoustid_result.get("mb_has_front_art"),
        )

        if caa_result.get("cover_art_error"):
            tlog.warning("cover_art returned error: %s", caa_result.get("cover_art_error"))

        # ------------------------------------------------------------------
        # Step 7 — Build the DB row
        # ------------------------------------------------------------------
        if progress_callback:
            progress_callback("writing")

        row = _build_db_row(
            file_path=path,
            file_hash=file_hash,
            file_size_bytes=file_size_bytes,
            file_modified_at=file_modified_at,
            tags=tags,
            acoustid=acoustid_result,
            discogs=discogs_result,
            itunes=itunes_result,
            caa=caa_result,
            essentia=essentia_result,
        )

        # ------------------------------------------------------------------
        # Step 8 — UPSERT into tracks
        # ------------------------------------------------------------------
        try:
            db.execute(_INSERT_SQL, row)
            db.commit()
            tlog.info("Wrote track: %s", row.get("resolved_title"))
        except Exception as exc:
            tlog.error("SQLite write failed: %s", exc)
            return None

        # ------------------------------------------------------------------
        # Step 9 — Embeddings write (optional; gated on essentia embedding)
        # ------------------------------------------------------------------
        embedding = essentia_result.get("embedding") if essentia_result else None
        if embedding is not None:
            try:
                from backend.database import _VEC_AVAILABLE

                if _VEC_AVAILABLE:
                    import struct

                    vec_bytes = struct.pack(f"{len(embedding)}f", *embedding)
                    cursor = db.execute("SELECT id FROM tracks WHERE file_path = ?", (path,))
                    track_id = cursor.fetchone()["id"]
                    db.execute("DELETE FROM vec_tracks WHERE track_id = ?", (track_id,))
                    db.execute(
                        "INSERT INTO vec_tracks(track_id, embedding) VALUES (?, ?)",
                        (track_id, vec_bytes),
                    )
                    db.commit()
            except Exception as exc:
                tlog.warning("vec_tracks write failed (non-fatal): %s", exc)

        if progress_callback:
            progress_callback("done")

        return row

    except Exception as exc:
        tlog.error("Unexpected error: %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# import_tracks — batch entry point
# ---------------------------------------------------------------------------


def import_tracks(
    paths: list[str | Path],
    db: sqlite3.Connection,
    config: PipelineConfig,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> None:
    """
    Import a list of audio files.

    File discovery (walking the folder, filtering by extension) belongs in
    the calling script — this function only accepts a pre-built list.

    on_progress(done, total, current_path) is called after each track completes,
    whether it was skipped, written, or errored.
    """
    total = len(paths)
    for i, path in enumerate(paths):
        try:
            import_track(path, db, config)
        except Exception as exc:
            # import_track should never raise, but guard defensively
            logger.error("Unhandled exception for %s: %s", path, exc, exc_info=True)
        if on_progress:
            on_progress(i + 1, total, str(path))
