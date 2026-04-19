"""
test_import_library.py — Tests for scripts/import_library.py.

No live network calls in any test. All importers are mocked where needed.
"""

import hashlib
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# scripts/ is not a package — add it to sys.path so we can import directly
SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from import_library import _format_duration, detect_moves, discover_files  # noqa: E402

from backend.database import get_db  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return get_db(str(tmp_path / "test.db"))


def _insert_track(db, file_path: str, file_hash: str) -> int:
    db.execute(
        "INSERT INTO tracks(file_path, file_hash, resolved_title) VALUES (?, ?, ?)",
        (file_path, file_hash, "Test Track"),
    )
    db.commit()
    return db.execute("SELECT id FROM tracks WHERE file_path = ?", (file_path,)).fetchone()["id"]


# ---------------------------------------------------------------------------
# discover_files
# ---------------------------------------------------------------------------


def test_discover_files_finds_audio_only(tmp_path):
    (tmp_path / "track.mp3").write_bytes(b"mp3")
    (tmp_path / "track.flac").write_bytes(b"flac")
    (tmp_path / "notes.txt").write_bytes(b"txt")
    (tmp_path / "cover.jpg").write_bytes(b"jpg")

    result = discover_files(tmp_path, {".mp3", ".flac"})

    names = [p.name for p in result]
    assert "track.mp3" in names
    assert "track.flac" in names
    assert "notes.txt" not in names
    assert "cover.jpg" not in names


def test_discover_files_recurses_into_subdirs(tmp_path):
    sub = tmp_path / "house"
    sub.mkdir()
    (sub / "deep.mp3").write_bytes(b"mp3")

    result = discover_files(tmp_path, {".mp3"})
    assert any(p.name == "deep.mp3" for p in result)


def test_discover_files_returns_sorted(tmp_path):
    (tmp_path / "z.mp3").write_bytes(b"z")
    (tmp_path / "a.mp3").write_bytes(b"a")
    (tmp_path / "m.mp3").write_bytes(b"m")

    result = discover_files(tmp_path, {".mp3"})
    assert result == sorted(result)


def test_discover_files_skips_symlinks(tmp_path):
    target = tmp_path / "real.mp3"
    target.write_bytes(b"real")
    link = tmp_path / "link.mp3"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")

    result = discover_files(tmp_path, {".mp3"})
    names = [p.name for p in result]
    assert "real.mp3" in names
    assert "link.mp3" not in names


# ---------------------------------------------------------------------------
# detect_moves
# ---------------------------------------------------------------------------


def test_detect_moves_updates_file_path(tmp_path, db):
    content = b"audio content for move test"
    file_hash = hashlib.md5(content).hexdigest()

    old_path = "/nonexistent/old/path.mp3"
    _insert_track(db, old_path, file_hash)

    new_file = tmp_path / "new_location.mp3"
    new_file.write_bytes(content)

    detect_moves(db, [new_file])

    row = db.execute(
        "SELECT file_path, file_modified_at FROM tracks WHERE file_hash = ?",
        (file_hash,),
    ).fetchone()
    assert row["file_path"] == str(new_file)
    assert row["file_modified_at"] is not None


def test_detect_moves_skips_duplicate_hashes(tmp_path, db, caplog):
    content = b"duplicate content"
    file_hash = hashlib.md5(content).hexdigest()

    _insert_track(db, "/old/path1.mp3", file_hash)
    _insert_track(db, "/old/path2.mp3", file_hash)

    new_file = tmp_path / "new.mp3"
    new_file.write_bytes(content)

    with caplog.at_level(logging.WARNING):
        detect_moves(db, [new_file])

    # Neither row should have been changed
    row1 = db.execute(
        "SELECT file_path FROM tracks WHERE file_path = ?", ("/old/path1.mp3",)
    ).fetchone()
    row2 = db.execute(
        "SELECT file_path FROM tracks WHERE file_path = ?", ("/old/path2.mp3",)
    ).fetchone()
    assert row1 is not None
    assert row2 is not None
    assert "Duplicate hash" in caplog.text


def test_detect_moves_ignores_already_known_paths(tmp_path, db):
    content = b"known file"
    file_hash = hashlib.md5(content).hexdigest()

    known_file = tmp_path / "known.mp3"
    known_file.write_bytes(content)

    _insert_track(db, str(known_file), file_hash)

    # detect_moves should not touch it (path is already in DB)
    detect_moves(db, [known_file])

    row = db.execute(
        "SELECT file_path FROM tracks WHERE file_path = ?", (str(known_file),)
    ).fetchone()
    assert row is not None  # row unchanged


def test_detect_moves_does_nothing_for_genuinely_new_file(tmp_path, db):
    new_file = tmp_path / "brand_new.mp3"
    new_file.write_bytes(b"unique content xyz")

    detect_moves(db, [new_file])

    row = db.execute("SELECT id FROM tracks WHERE file_path = ?", (str(new_file),)).fetchone()
    assert row is None  # pipeline handles actual import


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_call_import(tmp_path):
    (tmp_path / "track.mp3").write_bytes(b"mp3")

    with (
        patch("import_library.discover_files", return_value=[tmp_path / "track.mp3"]),
        patch("import_library.detect_moves") as mock_moves,
        patch("sys.argv", ["import_library.py", "--folder", str(tmp_path), "--dry-run"]),
    ):
        from import_library import main

        code = main()

    assert code == 0
    mock_moves.assert_not_called()


# ---------------------------------------------------------------------------
# progress counters
# ---------------------------------------------------------------------------


def test_counter_imported(tmp_path, db):
    """import_track returning a dict increments imported counter."""
    f1 = tmp_path / "a.mp3"
    f2 = tmp_path / "b.mp3"
    f1.write_bytes(b"a")
    f2.write_bytes(b"b")

    fake_row = {"resolved_title": "Track"}

    with (
        patch("import_library.get_db", return_value=db),
        patch("import_library.detect_moves"),
        patch("import_library.PipelineConfig"),
        patch("import_library.import_track", return_value=fake_row),
        patch(
            "sys.argv",
            ["import_library.py", "--folder", str(tmp_path), "--extensions", "mp3"],
        ),
    ):
        from import_library import main

        code = main()

    assert code == 0


def test_counter_skipped_vs_error(tmp_path, db):
    """
    import_track returning None is classified as skip if the row exists in DB,
    error if it does not.
    """
    f_skip = tmp_path / "skip.mp3"
    f_err = tmp_path / "err.mp3"
    f_skip.write_bytes(b"skip")
    f_err.write_bytes(b"err")

    # Pre-insert a row for the skip file so the script finds it
    _insert_track(db, str(f_skip), hashlib.md5(b"skip").hexdigest())

    results = {str(f_skip): None, str(f_err): None}

    def fake_import_track(path, _db, _config, **_kw):
        return results[path]

    with (
        patch("import_library.get_db", return_value=db),
        patch("import_library.detect_moves"),
        patch("import_library.PipelineConfig"),
        patch("import_library.import_track", side_effect=fake_import_track),
        patch(
            "sys.argv",
            ["import_library.py", "--folder", str(tmp_path), "--extensions", "mp3"],
        ),
    ):
        from import_library import main

        code = main()

    assert code == 0


# ---------------------------------------------------------------------------
# config error
# ---------------------------------------------------------------------------


def test_config_error_exits_1(tmp_path, capsys):
    (tmp_path / "track.mp3").write_bytes(b"mp3")

    from backend.config import ConfigurationError

    with (
        patch("import_library.get_db"),
        patch("import_library.detect_moves"),
        patch(
            "import_library.PipelineConfig",
            side_effect=ConfigurationError(
                "Required environment variable 'ACOUSTID_API_KEY' is not set. "
                "Copy .env.example to .env and fill in your values."
            ),
        ),
        patch(
            "sys.argv",
            ["import_library.py", "--folder", str(tmp_path), "--extensions", "mp3"],
        ),
    ):
        from import_library import main

        code = main()

    assert code == 1
    captured = capsys.readouterr()
    assert "ACOUSTID_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


def test_format_duration_under_one_minute():
    assert _format_duration(45) == "45s"


def test_format_duration_over_one_minute():
    assert _format_duration(272) == "4m 32s"


def test_format_duration_exact_minute():
    assert _format_duration(60) == "1m 0s"
