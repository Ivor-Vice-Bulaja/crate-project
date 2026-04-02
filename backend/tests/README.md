# backend/tests/

All pytest tests for the backend.

## What belongs here

- `conftest.py` — Shared fixtures: in-memory test database, test FastAPI client.
- `test_database.py` — Schema creation, upsert behaviour, hash-check logic.
- `test_api_tracks.py` — HTTP-level tests for the `/tracks` endpoint.
- `test_importer/` — Unit tests for each importer module (tags, fingerprinting, etc.)
- `fixtures/` — Static test assets: sample audio files, mock API responses.

## Running tests

```bash
uv run pytest                          # all tests
uv run pytest -v                       # verbose
uv run pytest --cov=backend            # with coverage
uv run pytest backend/tests/test_database.py  # single file
```

## What a fixture is

A fixture is a function that prepares something a test needs — like a database connection
or a configured API client — and tears it down after the test finishes. Pytest injects
fixtures into test functions automatically by matching parameter names.

## What conftest.py is

`conftest.py` is a special file pytest loads automatically. Any fixture defined here is
available to every test in the same directory and all subdirectories — no import needed.

## What coverage means

Coverage is the percentage of your code that gets executed during tests. 60% coverage
means at least 60 out of every 100 lines are exercised by at least one test. It is a
floor, not a goal — 100% coverage does not mean the tests are good, but very low
coverage means large areas of code are untested.
