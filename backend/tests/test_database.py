"""
Tests for database.py — schema creation and basic data operations.
"""

import sqlite3

from backend.database import init_db


def test_init_db_creates_crates_table(db: sqlite3.Connection) -> None:
    """
    init_db() must create the 'crates' table.

    Why test this?
    The crates schema is marked stable in CLAUDE.md. This test ensures
    that if someone accidentally changes or drops the CREATE TABLE
    statement, we find out immediately — not when a user tries to
    create their first crate.
    """
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crates'")
    row = cursor.fetchone()
    assert row is not None, "Expected 'crates' table to exist after init_db()"


def test_init_db_creates_all_core_tables(db: sqlite3.Connection) -> None:
    """
    init_db() must create tracks, crates, crate_tracks, and crate_corrections.
    """
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row["name"] for row in cursor.fetchall()}
    expected = {"tracks", "crates", "crate_tracks", "crate_corrections"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


def test_init_db_is_idempotent(db: sqlite3.Connection) -> None:
    """
    Calling init_db() twice must not raise an error.

    This matters because init_db() is called at application startup.
    If the database already exists (normal after first run), it must
    not crash or try to re-create tables that already exist.
    """
    init_db(db)  # called once by the fixture already; call again
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crates'")
    assert cursor.fetchone() is not None
