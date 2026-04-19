# backend/database.py
"""
database.py — SQLite connection, schema, and migrations.

This is the single source of truth for the database schema.
No schema SQL lives anywhere else in the codebase.

Schema is managed via PRAGMA user_version migrations:
  Migration 1 — tracks table (full column inventory)
  Migration 2 — vec_tracks virtual table (sqlite-vec; skipped if unavailable)
  Migration 3 — indexes on tracks
  Migration 4 — crate management tables

Migration version note: versions 1, 3, 4 are always applied. Version 2 is only
applied when sqlite-vec is available at first initialisation. A database that was
initialised without vec (final user_version=4) will never apply migration 2 on a
later install of sqlite-vec — because the DB is already at version 3+. To add vec
to an existing no-vec database, add a new migration (e.g. version 5).
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_VEC_AVAILABLE = False  # set to True inside get_db() after successful extension load

# ---------------------------------------------------------------------------
# Migration SQL constants
# ---------------------------------------------------------------------------

_MIGRATION_1_TRACKS = """
CREATE TABLE IF NOT EXISTS tracks (
    -- File identity
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path                       TEXT    NOT NULL UNIQUE,
    file_hash                       TEXT,
    file_size_bytes                 INTEGER,
    file_modified_at                TEXT,

    -- Audio stream properties (mutagen)
    tag_file_format                 TEXT,
    tag_duration_seconds            REAL,
    tag_bitrate_bps                 INTEGER,
    tag_bitrate_mode                TEXT,
    tag_sample_rate_hz              INTEGER,
    tag_channels                    INTEGER,
    tag_bits_per_sample             INTEGER,
    tag_encoder_info                TEXT,
    tag_is_sketchy                  INTEGER,

    -- Tag fields (mutagen)
    tag_title                       TEXT,
    tag_artist                      TEXT,
    tag_album_artist                TEXT,
    tag_album                       TEXT,
    tag_label                       TEXT,
    tag_catalogue_no                TEXT,
    tag_genre                       TEXT,
    tag_comment                     TEXT,
    tag_isrc                        TEXT,
    tag_copyright                   TEXT,
    tag_year_id3v24                 TEXT,
    tag_year_id3v23                 TEXT,
    tag_date_released               TEXT,
    tag_date_original               TEXT,
    tag_date_vorbis                 TEXT,
    tag_date_mp4                    TEXT,
    tag_track_number                TEXT,
    tag_disc_number                 TEXT,
    tag_bpm                         TEXT,
    tag_key                         TEXT,
    tag_energy                      TEXT,
    tag_initial_key_txxx            TEXT,
    tag_has_embedded_art            INTEGER,
    tag_has_serato_tags             INTEGER,
    tag_has_traktor_tags            INTEGER,
    tag_has_rekordbox_tags          INTEGER,
    tag_id3_version                 TEXT,
    tag_format_type                 TEXT,
    tag_tags_present                INTEGER,
    tag_error                       TEXT,

    -- AcoustID
    acoustid_id                     TEXT,
    acoustid_score                  REAL,
    acoustid_match                  INTEGER,

    -- MusicBrainz
    mb_recording_id                 TEXT,
    mb_release_id                   TEXT,
    mb_artist_id                    TEXT,
    mb_release_group_id             TEXT,
    mb_release_group_type           TEXT,
    mb_title                        TEXT,
    mb_artist                       TEXT,
    mb_artist_sort_name             TEXT,
    mb_year                         INTEGER,
    mb_duration_s                   REAL,
    mb_isrc                         TEXT,
    mb_release_title                TEXT,
    mb_release_status               TEXT,
    mb_release_country              TEXT,
    mb_label                        TEXT,
    mb_catalogue_number             TEXT,
    mb_has_front_art                INTEGER,
    mb_genres                       TEXT,
    mb_tags                         TEXT,
    mb_lookup_error                 TEXT,

    -- Discogs
    discogs_release_id              INTEGER,
    discogs_master_id               INTEGER,
    discogs_confidence              TEXT,
    discogs_search_strategy         TEXT,
    discogs_url                     TEXT,
    discogs_title                   TEXT,
    discogs_year                    INTEGER,
    discogs_country                 TEXT,
    discogs_released                TEXT,
    discogs_released_formatted      TEXT,
    discogs_status                  TEXT,
    discogs_data_quality            TEXT,
    discogs_notes                   TEXT,
    discogs_artists_sort            TEXT,
    discogs_num_for_sale            INTEGER,
    discogs_lowest_price            REAL,
    discogs_label_id                INTEGER,
    discogs_label                   TEXT,
    discogs_catno                   TEXT,
    discogs_label_entity_type       TEXT,
    discogs_artists                 TEXT,
    discogs_genres                  TEXT,
    discogs_styles                  TEXT,
    discogs_styles_search           TEXT,
    discogs_format_names            TEXT,
    discogs_format_descs            TEXT,
    discogs_producers               TEXT,
    discogs_remixers                TEXT,
    discogs_extraartists_raw        TEXT,
    discogs_labels_raw              TEXT,
    discogs_tracklist               TEXT,
    discogs_barcodes                TEXT,
    discogs_matrix_numbers          TEXT,
    discogs_have                    INTEGER,
    discogs_want                    INTEGER,
    discogs_rating_avg              REAL,
    discogs_rating_count            INTEGER,
    discogs_master_year             INTEGER,
    discogs_master_most_recent_id   INTEGER,
    discogs_master_url              TEXT,
    discogs_lookup_timestamp        TEXT,
    discogs_error                   TEXT,

    -- iTunes
    itunes_track_id                 INTEGER,
    itunes_artist_id                INTEGER,
    itunes_collection_id            INTEGER,
    itunes_confidence               TEXT,
    itunes_track_name               TEXT,
    itunes_artist_name              TEXT,
    itunes_collection_name          TEXT,
    itunes_release_date             TEXT,
    itunes_track_time_ms            INTEGER,
    itunes_disc_count               INTEGER,
    itunes_disc_number              INTEGER,
    itunes_track_count              INTEGER,
    itunes_track_number             INTEGER,
    itunes_genre                    TEXT,
    itunes_track_explicit           TEXT,
    itunes_is_streamable            INTEGER,
    itunes_artwork_url              TEXT,
    itunes_track_url                TEXT,
    itunes_artist_url               TEXT,
    itunes_collection_url           TEXT,
    itunes_collection_artist_id     INTEGER,
    itunes_collection_artist_name   TEXT,
    itunes_search_strategy          TEXT,
    itunes_country                  TEXT,
    itunes_lookup_timestamp         TEXT,
    itunes_error                    TEXT,

    -- Cover Art Archive
    caa_url                         TEXT,
    caa_source                      TEXT,
    caa_lookup_timestamp            TEXT,
    caa_error                       TEXT,

    -- Essentia: rhythm / BPM
    es_bpm                          REAL,
    es_bpm_confidence               REAL,
    es_beat_ticks                   TEXT,
    es_bpm_estimates                TEXT,
    es_bpm_intervals                TEXT,

    -- Essentia: key / harmony
    es_key                          TEXT,
    es_key_scale                    TEXT,
    es_key_strength                 REAL,
    es_tuning_frequency_hz          REAL,
    es_tuning_cents                 REAL,

    -- Essentia: loudness / dynamics
    es_integrated_loudness          REAL,
    es_loudness_range               REAL,
    es_dynamic_complexity           REAL,
    es_dynamic_complexity_loudness  REAL,

    -- Essentia: spectral / timbral
    es_spectral_centroid_hz         REAL,
    es_sub_bass_ratio               REAL,
    es_high_freq_ratio              REAL,
    es_mfcc_mean                    TEXT,
    es_mfcc_var                     TEXT,
    es_bark_bands_mean              TEXT,

    -- Essentia: rhythm / onset
    es_danceability                 REAL,
    es_danceability_dfa             TEXT,
    es_onset_times                  TEXT,
    es_onset_rate                   REAL,

    -- Essentia: pitch (optional, slow)
    es_pitch_frames                 TEXT,
    es_pitch_confidence_frames      TEXT,

    -- Essentia: ML genre
    es_genre_probabilities          TEXT,
    es_genre_top_labels             TEXT,
    es_genre_top_labels_search      TEXT,

    -- Essentia: ML mood
    es_arousal                      REAL,
    es_valence                      REAL,
    es_mood_aggressive              REAL,
    es_mood_happy                   REAL,
    es_mood_party                   REAL,
    es_mood_relaxed                 REAL,
    es_mood_sad                     REAL,

    -- Essentia: ML instrument / theme
    es_instrument_probabilities     TEXT,
    es_instrument_top_labels        TEXT,
    es_moodtheme_probabilities      TEXT,
    es_moodtheme_top_labels         TEXT,

    -- Essentia: ML danceability / voice
    es_ml_danceability              REAL,
    es_voice_probability            REAL,
    es_voice_probability_musicnn    REAL,

    -- Essentia: meta
    es_version                      TEXT,
    es_analysis_timestamp           TEXT,
    es_analysis_error               TEXT,

    -- Resolved canonical fields (computed from fallback chains by the pipeline)
    resolved_title                  TEXT,
    resolved_artist                 TEXT,
    resolved_bpm                    REAL,
    resolved_key                    TEXT,
    resolved_label                  TEXT,
    resolved_year                   INTEGER,
    resolved_artwork_url            TEXT,

    -- Usage
    last_played_at                  TEXT,
    play_count                      INTEGER,

    -- Import status timestamps
    imported_at                     TEXT,
    tags_imported_at                TEXT,
    acoustid_imported_at            TEXT,
    discogs_imported_at             TEXT,
    itunes_imported_at              TEXT,
    caa_imported_at                 TEXT,
    essentia_imported_at            TEXT
);
"""

_MIGRATION_2_VEC = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_tracks USING vec0(
    track_id  INTEGER PRIMARY KEY,
    embedding FLOAT[1280] distance_metric=cosine
);
"""

_MIGRATION_3_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_file_path ON tracks(file_path);
CREATE INDEX IF NOT EXISTS idx_tracks_file_hash ON tracks(file_hash);
CREATE INDEX IF NOT EXISTS idx_tracks_resolved_bpm ON tracks(resolved_bpm);
CREATE INDEX IF NOT EXISTS idx_tracks_resolved_key ON tracks(resolved_key);
CREATE INDEX IF NOT EXISTS idx_tracks_resolved_label ON tracks(resolved_label);
CREATE INDEX IF NOT EXISTS idx_tracks_resolved_year ON tracks(resolved_year);
CREATE INDEX IF NOT EXISTS idx_tracks_resolved_artist ON tracks(resolved_artist);
CREATE INDEX IF NOT EXISTS idx_tracks_resolved_title ON tracks(resolved_title);
CREATE INDEX IF NOT EXISTS idx_tracks_acoustid_id ON tracks(acoustid_id);
CREATE INDEX IF NOT EXISTS idx_tracks_acoustid_matched ON tracks(acoustid_id) WHERE acoustid_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tracks_essentia_ready ON tracks(es_bpm, es_integrated_loudness) WHERE es_bpm IS NOT NULL;
"""

_MIGRATION_4_CRATES = """
CREATE TABLE IF NOT EXISTS crates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crate_tracks (
    crate_id    TEXT    REFERENCES crates(id) ON DELETE CASCADE,
    track_id    INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    added_by    TEXT    DEFAULT 'ai',
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (crate_id, track_id)
);

CREATE TABLE IF NOT EXISTS crate_corrections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    crate_id     TEXT    REFERENCES crates(id),
    track_id     INTEGER REFERENCES tracks(id),
    action       TEXT,
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    """
    Attempt to load the sqlite-vec extension.
    Returns True on success, False if unavailable.
    Logs a warning but does not raise on failure.
    """
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except ImportError:
        logger.warning(
            "sqlite-vec not installed — vector search disabled. " "Run: uv add sqlite-vec"
        )
        return False
    except Exception as exc:
        conn.enable_load_extension(False)
        logger.warning("sqlite-vec load failed: %s — vector search disabled", exc)
        return False


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")


def _build_migrations(vec_available: bool) -> list[tuple[int, str]]:
    """
    Return the ordered list of (version, sql) migration pairs.
    Migration 2 (vec_tracks) is only included when sqlite-vec is available.

    Version numbering: 1, 3, 4 are always applied. 2 is only applied when vec
    is available at first initialisation. If a DB was created without vec
    (final user_version=4), migration 2 will never be applied because the DB is
    already past version 2. Add a new migration (e.g. version 5) to backfill
    vec_tracks in that scenario.
    """
    migrations = [
        (1, _MIGRATION_1_TRACKS),
        (3, _MIGRATION_3_INDEXES),
        (4, _MIGRATION_4_CRATES),
    ]
    if vec_available:
        migrations.insert(1, (2, _MIGRATION_2_VEC))
    return sorted(migrations, key=lambda x: x[0])


def _run_migrations(conn: sqlite3.Connection, vec_available: bool) -> None:
    """
    Apply any pending migrations in version order.

    executescript() is used for each migration — it issues an implicit COMMIT
    before running, so do not wrap migration SQL in BEGIN/COMMIT.
    PRAGMA user_version cannot be set inside an explicit transaction, but since
    executescript() already committed, the bare execute() here is safe.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in _build_migrations(vec_available):
        if version > current:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
            logger.debug("Applied migration %d", version)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    Open and configure a SQLite connection, run pending migrations, and return it.

    The caller is responsible for closing the connection. Typical usage:

        conn = get_db()
        try:
            ...
        finally:
            conn.close()

    For FastAPI dependency injection use a yield-based wrapper in backend/deps.py
    (not implemented here — belongs in Phase 3 when FastAPI is wired up).

    Args:
        db_path: Path to the database file. Defaults to the value from config
                 (DB_PATH environment variable). Pass ":memory:" for tests.
    """
    from backend.config import settings  # lazy import — avoids circular deps

    path = db_path if db_path is not None else settings.db_path
    conn = sqlite3.connect(str(path))
    _configure_connection(conn)
    vec_ok = _load_sqlite_vec(conn)
    _run_migrations(conn, vec_available=vec_ok)
    return conn


# ---------------------------------------------------------------------------
# Legacy shim — remove once all callers are updated
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    """
    Deprecated. Use get_db() which now handles migrations internally.
    This shim keeps existing tests green while the codebase is updated.
    """
    _run_migrations(conn, vec_available=False)
