# scripts/

One-off utility scripts. Not part of the application — just tools for development
and maintenance tasks.

## What belongs here

- `run_evals.py` — Runs eval cases against a prompt and reports pass/fail
- `import_folder.py` — Manually trigger an import of a music folder
- `reset_db.py` — Drop and recreate the database (dev use only)
- `check_deps.py` — Verify all optional dependencies (Essentia, etc.) are installed

## Rules

- Every script should have a `--help` flag explaining what it does
- Scripts should never be imported by the application — they are standalone tools
- Do not put business logic here; scripts call into `backend/` modules
