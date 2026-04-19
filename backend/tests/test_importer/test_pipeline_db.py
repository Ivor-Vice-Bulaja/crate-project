"""
test_pipeline_db.py — Integration tests for import_track() with a real SQLite DB.

All network importers are mocked. The file system fixture is read for real
so tag extraction runs on actual bytes.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import PipelineConfig
from backend.database import get_db
from backend.importer.pipeline import import_track

FIXTURE = Path(__file__).parent.parent / "fixtures" / "short.mp3"


@pytest.fixture
def db(tmp_path):
    return get_db(str(tmp_path / "test.db"))


@pytest.fixture
def config():
    """PipelineConfig with no network credentials (importers are mocked)."""
    with patch("backend.config.PipelineConfig.__post_init__"):
        cfg = PipelineConfig.__new__(PipelineConfig)
        from backend.config import (
            AcoustIDConfig,
            CoverArtConfig,
            DiscogsConfig,
            EssentiaConfig,
            ItunesConfig,
        )

        cfg.acoustid = AcoustIDConfig.__new__(AcoustIDConfig)
        cfg.acoustid.acoustid_api_key = "test"
        cfg.acoustid.acoustid_timeout = 10
        cfg.acoustid.mb_contact = "test"
        cfg.acoustid.mb_rate_limit = False
        cfg.acoustid.fetch_label = False
        cfg.discogs = DiscogsConfig()
        cfg.itunes = ItunesConfig()
        cfg.cover_art = CoverArtConfig()
        cfg.essentia = EssentiaConfig()
        cfg.max_workers = 3
        cfg.discogs_client = None
        return cfg


def _mock_all_importers(
    discogs_result=None, acoustid_result=None, itunes_result=None, caa_result=None
):
    """Context manager stack that mocks all network importers."""
    if acoustid_result is None:
        acoustid_result = {}
    if discogs_result is None:
        discogs_result = {}
    if itunes_result is None:
        itunes_result = {}
    if caa_result is None:
        caa_result = {
            "cover_art_url": None,
            "cover_art_source": None,
            "cover_art_lookup_timestamp": "2026-01-01T00:00:00+00:00",
            "cover_art_error": None,
        }
    return (
        patch("backend.importer.pipeline.identify_track", return_value=acoustid_result),
        patch("backend.importer.pipeline.fetch_discogs_metadata", return_value=discogs_result),
        patch("backend.importer.pipeline.fetch_itunes", return_value=itunes_result),
        patch("backend.importer.pipeline.fetch_cover_art", return_value=caa_result),
        patch("backend.importer.pipeline._ESSENTIA_AVAILABLE", False),
    )


# ---------------------------------------------------------------------------
# Basic write
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_full_pipeline_writes_row(db, config):
    """import_track() must write at least one row to tracks."""
    patches = _mock_all_importers()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = import_track(str(FIXTURE), db, config)

    assert result is not None
    row = db.execute("SELECT * FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()
    assert row is not None


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_resolved_title_non_null(db, config):
    """resolved_title is never NULL — falls back to filename stem at minimum."""
    patches = _mock_all_importers()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = import_track(str(FIXTURE), db, config)

    assert result is not None
    assert result["resolved_title"] is not None


# ---------------------------------------------------------------------------
# UPSERT preserves id
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_upsert_preserves_id(db, config):
    """Re-importing a changed file must not change the track's id."""
    patches = _mock_all_importers()

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        import_track(str(FIXTURE), db, config)

    row1 = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()
    assert row1 is not None

    # Force re-import by resetting stored mtime
    db.execute(
        "UPDATE tracks SET file_modified_at = '0' WHERE file_path = ?",
        (str(FIXTURE),),
    )
    db.commit()

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        import_track(str(FIXTURE), db, config)

    row2 = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()

    assert row1["id"] == row2["id"]


# ---------------------------------------------------------------------------
# Crate membership survives re-import
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_crate_membership_survives_reimport(db, config):
    """crate_tracks row must not be deleted on re-import (no INSERT OR REPLACE)."""
    patches = _mock_all_importers()

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        import_track(str(FIXTURE), db, config)

    track_id = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()[
        "id"
    ]

    db.execute("INSERT INTO crates(id, name, description) VALUES ('c1', 'Test', 'desc')")
    db.execute("INSERT INTO crate_tracks(crate_id, track_id) VALUES ('c1', ?)", (track_id,))
    db.commit()

    # Force re-import
    db.execute(
        "UPDATE tracks SET file_modified_at = '0' WHERE file_path = ?",
        (str(FIXTURE),),
    )
    db.commit()

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        import_track(str(FIXTURE), db, config)

    count = db.execute(
        "SELECT COUNT(*) FROM crate_tracks WHERE track_id = ?", (track_id,)
    ).fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# Skip logic — no importers called on unchanged file
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_skip_unchanged_file_calls_no_importers(db, config):
    """After a successful import, re-importing the same unchanged file skips all importers."""
    patches = _mock_all_importers()
    with patches[0] as mock_acoustid, patches[1], patches[2], patches[3], patches[4]:
        import_track(str(FIXTURE), db, config)

    with patches[0] as mock_acoustid, patches[1], patches[2], patches[3], patches[4]:
        result = import_track(str(FIXTURE), db, config)
        assert result is None  # hash-hit skip
        assert mock_acoustid.call_count == 0


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_empty_acoustid_result_does_not_abort(db, config):
    """acoustid returning {} (empty) should not prevent the row from being written."""
    patches = _mock_all_importers(acoustid_result={})
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = import_track(str(FIXTURE), db, config)

    assert result is not None
    row = db.execute("SELECT * FROM tracks WHERE file_path = ?", (str(FIXTURE),)).fetchone()
    assert row is not None


@pytest.mark.skipif(not FIXTURE.exists(), reason="test fixture not found")
def test_import_track_returns_none_on_db_write_failure(db, config):
    """If the SQLite write fails, import_track returns None without raising."""
    patches = _mock_all_importers()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patch("backend.importer.pipeline._INSERT_SQL", "INVALID SQL ;;"),
    ):
        result = import_track(str(FIXTURE), db, config)

    assert result is None  # error caught, not raised
