# Crate

A smart music library application for DJs. Every track in your library is automatically
analysed and classified. You define collections (crates) in plain language — "dark, driving
techno between 132–138 BPM" — and the app populates and maintains them using AI.

Target user: techno and house DJs with libraries of 5,000–20,000 tracks.
Local-first: all data stays on your machine. No cloud, no accounts.

---

## Prerequisites

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node 20+** — [nodejs.org](https://nodejs.org/)
- **uv** — Python package manager (replaces pip + venv)

### Installing uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy BypassScope -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## Installation

```bash
git clone https://github.com/your-username/crate-project.git
cd crate-project

# Copy the environment template and fill in your API keys
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY and ACOUSTID_API_KEY

# Install Python dependencies (runtime + dev tools)
uv sync --extra dev

# Install frontend dependencies
cd frontend && npm install && cd ..
```

---

## Running the application

**Backend (FastAPI server):**
```bash
uv run uvicorn backend.main:app --reload
# Server starts at http://localhost:8000
# --reload means the server restarts automatically when you save a file
```

**Frontend (React dev server):**
```bash
cd frontend
npm run dev
# Opens at http://localhost:5173
# Changes appear instantly without refreshing (hot reload)
```

---

## Running tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage report
uv run pytest --cov=backend

# Run a specific test file
uv run pytest backend/tests/test_database.py
```

---

## Running the linter

```bash
# Check for issues
uv run ruff check .

# Auto-fix safe issues (unused imports, etc.)
uv run ruff check . --fix

# Check formatting
uv run ruff format --check .

# Auto-format
uv run ruff format .

# Type check
uv run pyright
```

---

## Project structure

```
crate-project/
├── backend/                # Python backend (FastAPI)
│   ├── main.py             # App entry point — registers routers
│   ├── config.py           # Settings loaded from .env
│   ├── database.py         # SQLite connection and schema
│   ├── api/                # HTTP route handlers (tracks, crates, search)
│   ├── importer/           # Import pipeline (tags, AcoustID, Essentia, etc.)
│   ├── crates/             # AI crate-fill pipeline
│   └── tests/              # pytest test suite
├── frontend/               # React frontend (Vite)
│   └── src/
│       ├── views/          # Full-page components (Library, Crates, SetPlanner)
│       └── components/     # Reusable UI components
├── prompts/                # Versioned AI prompt files
├── evals/                  # Prompt quality test cases
├── scripts/                # One-off utility scripts
├── docs/                   # Research notes and architecture decisions
├── .github/workflows/      # GitHub Actions CI pipeline
├── pyproject.toml          # Python project config (dependencies, tool settings)
├── uv.lock                 # Locked dependency versions (commit this)
├── .env.example            # Environment variable template (commit this)
└── .pre-commit-config.yaml # Git hook configuration
```

---

## Contributing

### Branching strategy

```
main    — always working. Never commit directly to main.
dev     — integration branch. Merge feature branches here first.
feature/description  — new features
fix/description      — bug fixes
```

**Creating a feature branch:**
```bash
git checkout dev
git pull origin dev
git checkout -b feature/my-feature-name
# ... make changes ...
git push origin feature/my-feature-name
# Open a pull request to dev on GitHub
```

**Why this matters:**
`main` is always in a deployable state. If you commit directly to `main` and break
something, there is no safe version to fall back to. Feature branches let you work
without affecting anyone else, and pull requests give you a chance to review changes
before they merge.

### Running CI locally

You can run the same checks that CI runs, before pushing:

```bash
# Run pre-commit on all files
uv run pre-commit run --all-files

# Run the full test suite with coverage
uv run pytest --cov=backend --cov-fail-under=60

# Run frontend checks
cd frontend && npm run lint && npm run build
```

### Dependency management

To add a new runtime dependency:
```bash
# Edit pyproject.toml, add to [project.dependencies]
uv lock          # regenerate the lock file
uv sync          # install into .venv
```

To add a dev-only dependency:
```bash
# Edit pyproject.toml, add to [project.optional-dependencies.dev]
uv lock && uv sync --extra dev
```
