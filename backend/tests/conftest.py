"""
conftest.py — Shared pytest fixtures for all backend tests.

What is a fixture?
A fixture is a function that prepares something a test needs — like a database
connection or an API client — and tears it down after the test is done.
pytest injects fixtures into test functions automatically by matching
parameter names. You never call fixtures yourself; pytest calls them for you.

What is conftest.py?
conftest.py is a special file that pytest loads automatically before running
tests. Any fixture defined here is available to every test in this directory
and all subdirectories without needing an explicit import. It's the right
place to put shared infrastructure that multiple test files need.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app


@pytest.fixture
def db() -> sqlite3.Connection:
    """
    Provide a fresh in-memory SQLite database for each test.

    Using ':memory:' means:
    - Tests are completely isolated — no file on disk, nothing to clean up
    - Each test starts with a pristine, empty database
    - Tests run faster (no disk I/O)

    get_db(':memory:') configures the connection and applies all migrations.
    """
    conn = get_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def client() -> TestClient:
    """
    Provide a test HTTP client for the FastAPI application.

    TestClient wraps the FastAPI app so you can make HTTP requests
    (GET, POST, etc.) in tests without starting a real server.
    Requests go directly through the ASGI interface — it's as close
    to real as possible without a network.
    """
    return TestClient(app)
