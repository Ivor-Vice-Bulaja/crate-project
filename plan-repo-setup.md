# Task: Set Up the Crate Project Repository

## Context

Read CLAUDE.md before starting. This task is about setting up the project
structure, tooling, and CI/CD pipeline before any product code is written.
Getting this right now means every future coding session starts from a clean,
consistent, professional foundation.

I have no prior experience with repository structure or CI/CD. Explain every
decision you make and why it matters. Do not assume I know what any tool does —
tell me.

---

## What to build

A complete, ready-to-code project repository for Crate: a Python backend
(FastAPI) and React frontend application. The repository should reflect
professional standards, be easy to work in, and catch problems automatically
before they reach the main codebase.

---

## The application

- **Backend**: Python 3.11+, FastAPI, SQLite, Essentia, sentence-transformers
- **Frontend**: React (Vite), plain JavaScript (no TypeScript for now)
- **Communication**: REST API between frontend and backend
- **Deployment target**: local desktop application for now, potentially packaged
  later — not a web server

---

## Deliverables

Work through these in order. Explain what you are doing at each step.

---

### 1. Repository layout

Create the full directory structure with placeholder files. Every directory
should have a brief comment in a README explaining what belongs there.

```
crate-project/
├── backend/
│   ├── api/
│   ├── importer/
│   ├── crates/
│   ├── tests/
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   ├── components/
│   │   └── App.jsx
│   └── package.json
├── prompts/
├── evals/
├── scripts/
├── docs/
├── .github/
│   └── workflows/
├── CLAUDE.md
├── CURRENT_STATE.md
├── .env.example
├── .gitignore
├── README.md
└── docker-compose.yml   (optional but recommended for consistent dev env)
```

---

### 2. Python environment and dependency management

Set up the Python environment properly.

- Use **pyproject.toml** as the single source of truth for the project.
  Explain what pyproject.toml is and why it replaces setup.py and requirements.txt.
- Use **uv** as the package manager. Explain what uv is, why it is faster and
  more reliable than pip, and how to install it.
- Define dependency groups:
  - `[project.dependencies]` — runtime dependencies (fastapi, uvicorn, sqlite-vec, etc.)
  - `[project.optional-dependencies]` with groups:
    - `analysis` — essentia, sentence-transformers (heavy, optional)
    - `dev` — testing, linting, formatting tools
- Create a **uv.lock** file for reproducible installs
- Explain how to install: `uv sync`, `uv sync --extra dev`, etc.

---

### 3. Code quality tooling

Install and configure the following. For each tool, explain what it does and
why it is in this stack:

**Ruff** — Python linter and formatter (replaces flake8, black, isort in one tool)
- Configure in pyproject.toml
- Set line length to 100
- Enable the following rule sets: E, F, I, N, UP, B, SIM
- Explain what each rule set catches

**Pre-commit** — runs checks automatically before every git commit
- Install pre-commit
- Create `.pre-commit-config.yaml` with:
  - ruff (lint + format)
  - trailing whitespace removal
  - end-of-file fixer
  - check for accidentally committed secrets (detect-secrets or similar)
  - check that .env is never committed
- Explain what pre-commit does and why it matters

**Pyright** — static type checker (explain what type checking is and why it
catches bugs that tests miss)
- Configure in pyproject.toml as pyrightconfig
- Set to basic mode (not strict — strict would be too demanding for a new codebase)

---

### 4. Testing framework

Set up **pytest** with sensible defaults.

- Configure in pyproject.toml
- Create the test directory structure:
  ```
  backend/tests/
  ├── conftest.py          # shared fixtures (test database, test client)
  ├── test_database.py     # schema creation, upsert, hash check
  ├── test_api_tracks.py   # GET /tracks endpoint
  ├── test_importer/
  │   └── test_tags.py     # tag reading on sample files
  └── fixtures/
      └── sample.mp3       # a real short audio file for integration tests

  Note: do NOT create test_scores.py — derived score formulas are not yet
  finalised and will be added in Phase 1 after validation on real tracks.
  ```
- Write the conftest.py with:
  - A test database fixture (in-memory SQLite, schema created fresh for each test)
  - A test FastAPI client fixture
- Write at least 3 real tests:
  - Test that `init_db()` creates the crates table (this schema is settled)
  - Test that the config module raises a clear error when a required env var is missing
  - Test that `GET /tracks` returns 200 with an empty list when no tracks exist
- Configure test coverage reporting (pytest-cov)
- Explain what a fixture is, what conftest.py is, and what coverage means

---

### 5. Git setup

- Initialise the git repository
- Create a **meaningful .gitignore** for this specific project:
  - Python: __pycache__, .venv, *.pyc, *.pyo, dist/, build/, .eggs/
  - Essentia model files (*.pb) — large binary files, not committed
  - The database file (crate.db) — user data, never committed
  - The music folder — never committed
  - Environment files (.env) — secrets, never committed
  - Frontend: node_modules/, dist/, .vite/
  - OS files: .DS_Store, Thumbs.db
  - IDE files: .vscode/settings.json (but commit .vscode/extensions.json)
- Create a **meaningful initial commit** — not just "initial commit"
- Explain the git branching strategy to use:
  - `main` — always working, never commit directly
  - `dev` — integration branch
  - feature branches named `feature/description`, bugfix branches `fix/description`
  - Explain why this matters and how to create and merge branches

---

### 6. GitHub Actions CI pipeline

Create `.github/workflows/ci.yml`. Explain what GitHub Actions is, what a
workflow is, what a job is, and what a step is.

The CI pipeline should run on every push to any branch and on every pull
request to main. It should do the following jobs in order:

**Job 1: lint**
```yaml
- Check out code
- Install uv
- Install dev dependencies
- Run ruff check (linting)
- Run ruff format --check (formatting)
- Run pyright (type checking)
```

**Job 2: test** (runs after lint passes)
```yaml
- Check out code
- Install uv
- Install dev + runtime dependencies (excluding analysis group — no Essentia in CI)
- Run pytest with coverage
- Upload coverage report as artifact
- Fail if coverage drops below 60%
```

**Job 3: frontend** (runs in parallel with lint)
```yaml
- Check out code
- Install Node 20
- npm install in frontend/
- npm run lint (eslint)
- npm run build (verify it builds without errors)
```

Explain:
- What a CI pipeline is and why it matters
- What "runs on ubuntu-latest" means
- Why Essentia is excluded from CI (binary dependencies, install time)
- What a coverage threshold means
- How to see the CI results on GitHub

---

### 7. Frontend tooling

Set up the React frontend with Vite.

```bash
cd frontend && npm create vite@latest . -- --template react
```

Then install and configure:

**ESLint** — JavaScript linter
- Configure with recommended rules + react rules
- Add a rule against console.log in production code
- Explain what ESLint does

**Prettier** — JavaScript formatter
- Configure with these settings: singleQuote, semicolons, 100 char line length
- Integrate with ESLint (eslint-plugin-prettier)

Add these npm scripts to package.json:
```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint src/",
  "format": "prettier --write src/",
  "preview": "vite preview"
}
```

---

### 8. Environment configuration

Create **.env.example** — the template that gets committed (no real secrets):

```
# Crate environment configuration
# Copy this file to .env and fill in your values
# NEVER commit .env to git

ANTHROPIC_API_KEY=your_key_here
ACOUSTID_API_KEY=your_key_here
MUSICBRAINZ_APP=CrateApp/0.1 (your@email.com)
DISCOGS_TOKEN=your_token_here

# Optional - Phase 2
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=

# Paths
DB_PATH=./crate.db
MUSIC_FOLDER=/absolute/path/to/your/music

# Development
LOG_LEVEL=INFO
```

Create a **config.py** module in the backend that:
- Loads .env using python-dotenv
- Defines a Settings class with all config values and their types
- Raises a clear error if required variables are missing
- Is imported by every module that needs config (single source of truth)
- Explain why centralising config matters

---

### 9. README.md

Write a proper README.md that covers:

- What Crate is (2–3 sentences)
- Prerequisites (Python 3.11+, Node 20+, uv)
- Installation:
  ```bash
  git clone ...
  cd crate
  cp .env.example .env
  # fill in .env values
  uv sync --extra dev
  cd frontend && npm install
  ```
- Running the backend: `uv run uvicorn backend.main:app --reload`
- Running the frontend: `cd frontend && npm run dev`
- Running tests: `uv run pytest`
- Running linting: `uv run ruff check .`
- Project structure (brief description of each top-level directory)
- Contributing: branch naming, how to run CI locally

---

### 10. VS Code workspace configuration

Create `.vscode/extensions.json` recommending:
- Python extension
- Pylance (Pyright language server)
- Ruff extension
- ESLint extension
- Prettier extension
- GitLens
- SQLite Viewer (for inspecting crate.db)

Create `.vscode/settings.json` (this one IS committed — project-wide settings):
- Set Python interpreter to the uv virtual environment
- Enable format on save with Ruff
- Enable format on save with Prettier for JS files
- Set default formatter per language
- Enable Pyright type checking

---

## Definition of done

The setup is complete when:

- [ ] `uv sync --extra dev` runs without errors
- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run pytest` runs and at least 3 tests pass
- [ ] `cd frontend && npm install && npm run build` succeeds
- [ ] `git commit` triggers pre-commit hooks and they all pass
- [ ] `.env` is listed in .gitignore and would be blocked from commit
- [ ] The GitHub Actions workflow file exists and is syntactically valid
      (validate with `act` locally or push to GitHub and check)
- [ ] `CLAUDE.md` and `.env.example` are committed but `crate.db` and `.env` are not

---

## What to explain as you go

For every tool you install, answer these three questions briefly:
1. What does this do?
2. Why is it in this project specifically?
3. How do I use it day-to-day?

I am not familiar with professional software development practices. Treat this
as teaching me the foundation I will build on for the rest of the project.
After this session I should understand why each piece exists, not just that it exists.
