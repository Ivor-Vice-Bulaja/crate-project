"""
Tests for backend/database.py — schema creation, migrations, and constraints.
"""

import sqlite3

import pytest

from backend.database import _run_migrations, get_db


def test_get_db_returns_connection() -> None:
    """get_db(':memory:') must return a sqlite3.Connection without raising."""
    conn = get_db(":memory:")
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_user_version_after_migration() -> None:
    """
    Final user_version must be 4 regardless of whether sqlite-vec is present.
    Migration 2 is inserted between 1 and 3, so the final version is still 4.
    """
    conn = get_db(":memory:")
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 4
    finally:
        conn.close()


def test_tracks_table_exists() -> None:
    """tracks table must exist after migration."""
    conn = get_db(":memory:")
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'"
        ).fetchone()
        assert row is not None, "Expected 'tracks' table to exist"
    finally:
        conn.close()


def test_tracks_table_has_required_columns() -> None:
    """tracks table must contain all non-nullable columns and key importer columns."""
    conn = get_db(":memory:")
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(tracks)").fetchall()}
        required = {
            "id",
            "file_path",
            # file identity
            "file_hash",
            "file_size_bytes",
            "file_modified_at",
            # mutagen stream
            "tag_file_format",
            "tag_duration_seconds",
            # mutagen tags
            "tag_title",
            "tag_artist",
            "tag_bpm",
            "tag_key",
            "tag_error",
            # acoustid
            "acoustid_id",
            "acoustid_score",
            "acoustid_match",
            # musicbrainz
            "mb_recording_id",
            "mb_title",
            "mb_artist",
            "mb_year",
            "mb_lookup_error",
            # discogs
            "discogs_release_id",
            "discogs_label",
            "discogs_catno",
            "discogs_styles_search",
            "discogs_error",
            # itunes
            "itunes_track_id",
            "itunes_artwork_url",
            "itunes_error",
            # cover art archive
            "caa_url",
            "caa_source",
            "caa_error",
            # essentia
            "es_bpm",
            "es_key",
            "es_key_scale",
            "es_integrated_loudness",
            "es_genre_top_labels_search",
            "es_analysis_error",
            # resolved fields
            "resolved_title",
            "resolved_artist",
            "resolved_bpm",
            "resolved_key",
            "resolved_label",
            "resolved_year",
            "resolved_artwork_url",
            # usage
            "last_played_at",
            "play_count",
            # import timestamps
            "imported_at",
            "tags_imported_at",
            "acoustid_imported_at",
            "discogs_imported_at",
            "itunes_imported_at",
            "caa_imported_at",
            "essentia_imported_at",
        }
        missing = required - cols
        assert not missing, f"Missing columns in tracks: {sorted(missing)}"
    finally:
        conn.close()


def test_crate_tables_exist() -> None:
    """crates, crate_tracks, and crate_corrections must all exist after migration."""
    conn = get_db(":memory:")
    try:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for name in ("crates", "crate_tracks", "crate_corrections"):
            assert name in tables, f"Expected '{name}' table to exist"
    finally:
        conn.close()


def test_vec_tracks_exists_when_sqlite_vec_installed() -> None:
    """vec_tracks virtual table must exist when sqlite-vec is available."""
    pytest.importorskip("sqlite_vec")
    conn = get_db(":memory:")
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_tracks'"
        ).fetchone()
        assert row is not None, "Expected 'vec_tracks' virtual table to exist"
    finally:
        conn.close()


def test_connection_produces_sqlite_row() -> None:
    """get_db() must configure row_factory=sqlite3.Row so columns are accessible by name."""
    conn = get_db(":memory:")
    try:
        row = conn.execute("SELECT 1 AS x").fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["x"] == 1
    finally:
        conn.close()


def test_migrations_are_idempotent() -> None:
    """Running _run_migrations a second time must not raise (all CREATE IF NOT EXISTS)."""
    conn = get_db(":memory:")
    try:
        _run_migrations(conn, vec_available=False)  # already applied; should be a no-op
    finally:
        conn.close()


def test_file_path_unique_constraint() -> None:
    """Inserting two rows with the same file_path must raise IntegrityError."""
    conn = get_db(":memory:")
    try:
        conn.execute("INSERT INTO tracks (file_path) VALUES ('test.mp3')")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO tracks (file_path) VALUES ('test.mp3')")
            conn.commit()
    finally:
        conn.close()


def test_foreign_key_constraint_on_crate_tracks() -> None:
    """
    Inserting into crate_tracks with a non-existent crate_id must raise IntegrityError.
    This verifies that PRAGMA foreign_keys=ON is active.
    """
    conn = get_db(":memory:")
    try:
        # Insert a real track first so track_id FK is satisfied
        conn.execute("INSERT INTO tracks (file_path) VALUES ('a.mp3')")
        conn.commit()
        track_id = conn.execute("SELECT id FROM tracks WHERE file_path='a.mp3'").fetchone()["id"]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO crate_tracks (crate_id, track_id) VALUES (?, ?)",
                ("nonexistent-crate", track_id),
            )
            conn.commit()
    finally:
        conn.close()
