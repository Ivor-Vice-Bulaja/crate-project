"""
database.py — SQLite connection and schema management.

Every other module that needs the database imports get_db() from here.
This is the single place where the connection is configured and the
schema is created.
"""

import sqlite3

from backend.config import settings


def get_db(db_path: str | None = None) -> sqlite3.Connection:
    """
    Open a SQLite connection with sensible defaults.

    Args:
        db_path: Override the database path. Used by tests to inject an
                 in-memory database (':memory:').

    Returns:
        A configured sqlite3.Connection.
    """
    path = db_path if db_path is not None else settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["column"]
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent read performance
    conn.execute("PRAGMA foreign_keys=ON")  # enforce foreign key constraints
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create all tables if they do not already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
    Call this once at application startup.
    """
    conn.executescript("""
        -- Crate tables are stable and implemented now.
        -- The tracks table schema is a draft — fields will be finalised
        -- in Phase 1 after all data sources have been researched.

        CREATE TABLE IF NOT EXISTS tracks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path   TEXT NOT NULL UNIQUE,
            file_hash   TEXT NOT NULL,
            title       TEXT,
            artist      TEXT,
            album       TEXT,
            year        INTEGER,
            bpm         REAL,
            key         TEXT,
            duration    REAL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS crates (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS crate_tracks (
            crate_id    TEXT REFERENCES crates(id) ON DELETE CASCADE,
            track_id    INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
            added_by    TEXT DEFAULT 'ai',
            added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (crate_id, track_id)
        );

        CREATE TABLE IF NOT EXISTS crate_corrections (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            crate_id     TEXT REFERENCES crates(id),
            track_id     INTEGER REFERENCES tracks(id),
            action       TEXT,
            corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
