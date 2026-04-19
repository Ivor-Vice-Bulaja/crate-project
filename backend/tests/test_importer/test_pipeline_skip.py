"""
test_pipeline_skip.py — Unit tests for _hash_file() and _check_skip().

These test the change-detection layer in isolation — no importers, no DB writes.
"""

import hashlib
import sqlite3

from backend.database import get_db
from backend.importer.pipeline import _check_skip, _hash_file

# ---------------------------------------------------------------------------
# _hash_file
# ---------------------------------------------------------------------------


def test_hash_file_returns_md5_hex(tmp_path):
    f = tmp_path / "track.mp3"
    f.write_bytes(b"hello world")
    result = _hash_file(str(f))
    expected = hashlib.md5(b"hello world").hexdigest()
    assert result == expected


def test_hash_file_consistent_across_calls(tmp_path):
    f = tmp_path / "track.mp3"
    f.write_bytes(b"x" * 200_000)
    assert _hash_file(str(f)) == _hash_file(str(f))


def test_hash_file_differs_on_different_content(tmp_path):
    a = tmp_path / "a.mp3"
    b = tmp_path / "b.mp3"
    a.write_bytes(b"aaaa")
    b.write_bytes(b"bbbb")
    assert _hash_file(str(a)) != _hash_file(str(b))


# ---------------------------------------------------------------------------
# _check_skip helpers
# ---------------------------------------------------------------------------


def _insert_track(db: sqlite3.Connection, path: str, mtime: str, hash_: str) -> None:
    """Insert a minimal tracks row so _check_skip has something to query."""
    db.execute(
        "INSERT INTO tracks (file_path, file_modified_at, file_hash) VALUES (?, ?, ?)",
        (path, mtime, hash_),
    )
    db.commit()


# ---------------------------------------------------------------------------
# _check_skip
# ---------------------------------------------------------------------------


def test_check_skip_new_file_returns_false(tmp_path):
    """A file not yet in the DB should not be skipped."""
    f = tmp_path / "new.mp3"
    f.write_bytes(b"new content")
    db = get_db(":memory:")
    assert _check_skip(str(f), db) is False


def test_check_skip_unchanged_mtime_returns_true(tmp_path):
    """If mtime matches the stored value, skip without hashing."""
    import os

    f = tmp_path / "track.mp3"
    f.write_bytes(b"audio data")
    current_mtime = str(os.stat(str(f)).st_mtime)

    db = get_db(":memory:")
    _insert_track(db, str(f), current_mtime, "somehash")

    assert _check_skip(str(f), db) is True


def test_check_skip_changed_mtime_same_content_returns_true(tmp_path):
    """
    mtime changed (e.g. touch) but hash matches → skip (content unchanged).
    """
    f = tmp_path / "track.mp3"
    f.write_bytes(b"audio data")
    real_hash = _hash_file(str(f))

    # Store a fake old mtime so the mtime check fails
    db = get_db(":memory:")
    _insert_track(db, str(f), "0.0", real_hash)

    assert _check_skip(str(f), db) is True


def test_check_skip_changed_mtime_changed_content_returns_false(tmp_path):
    """mtime changed AND hash changed → do not skip (file genuinely changed)."""
    f = tmp_path / "track.mp3"
    f.write_bytes(b"original content")

    db = get_db(":memory:")
    _insert_track(db, str(f), "0.0", "oldhash")

    assert _check_skip(str(f), db) is False
