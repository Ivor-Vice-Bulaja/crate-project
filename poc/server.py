"""
poc/server.py — Minimal POC server for testing the import pipeline.

Exposes three endpoints:
  POST /import          — accepts a list of file paths, runs the pipeline, returns per-file results
  POST /import-folder   — accepts a folder path, discovers files, runs move detection, imports all
  GET  /tracks          — returns all tracks in the DB as JSON

Run from the project root (WSL2):
  uv run python poc/server.py
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from backend.config import ConfigurationError, PipelineConfig
from backend.database import get_db
from backend.importer.pipeline import import_track

# import_library helpers — discover_files and detect_moves live there
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from import_library import detect_moves, discover_files  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("poc")

DB_PATH = "./crate.db"


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _get_all_tracks() -> list[dict]:
    db = get_db(DB_PATH)
    try:
        rows = db.execute("SELECT * FROM tracks ORDER BY id DESC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()


DEFAULT_EXTENSIONS = {".mp3", ".flac", ".wav", ".aiff", ".aif"}


def _import_folder(folder: str, extensions: set[str] | None = None) -> dict:
    """Discover files, run move detection, then import. Returns a summary dict."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return {"error": f"Not a directory: {folder}"}

    exts = extensions or DEFAULT_EXTENSIONS
    paths = discover_files(folder_path, exts)

    db = get_db(DB_PATH)
    try:
        try:
            config = PipelineConfig()
        except ConfigurationError as exc:
            return {"error": str(exc)}

        detect_moves(db, paths)

        imported = skipped = errors = 0
        for path in paths:
            result = import_track(str(path), db, config)
            if result is not None:
                imported += 1
            else:
                row = db.execute(
                    "SELECT id FROM tracks WHERE file_path = ?", (str(path),)
                ).fetchone()
                if row is not None:
                    skipped += 1
                else:
                    errors += 1
    finally:
        db.close()

    return {
        "folder": folder,
        "discovered": len(paths),
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


def _import_files(paths: list[str]) -> list[dict]:
    db = get_db(DB_PATH)
    config = PipelineConfig()
    results = []
    try:
        for path in paths:
            logger.info("importing: %s", path)
            # Check if already in DB before import to distinguish skip vs error
            existing = db.execute(
                "SELECT file_modified_at, file_hash FROM tracks WHERE file_path = ?", (path,)
            ).fetchone()
            row = import_track(path, db, config)
            if row:
                results.append({"path": path, "status": "ok", "id": row.get("id")})
            elif existing:
                results.append({"path": path, "status": "skipped (unchanged)"})
            else:
                results.append({"path": path, "status": "error — check server log"})
    except Exception as e:
        logger.exception("import failed")
        results.append({"path": str(paths), "status": "error", "error": str(e)})
    finally:
        db.close()
    return results


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # suppress default access log
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/tracks":
            self._send_json(_get_all_tracks())
        elif parsed.path == "/" or parsed.path == "/index.html":
            html_path = Path(__file__).parent / "index.html"
            self._send_html(html_path.read_text(encoding="utf-8"))
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body) if body else {}
        except Exception as e:
            self._send_json({"error": f"invalid JSON: {e}"}, 400)
            return

        if parsed.path == "/import":
            paths = data.get("paths", [])
            if not paths:
                self._send_json({"error": "no paths provided"}, 400)
                return
            try:
                results = _import_files(paths)
                self._send_json(results)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif parsed.path == "/import-folder":
            folder = data.get("folder", "").strip()
            if not folder:
                self._send_json({"error": "folder is required"}, 400)
                return
            try:
                result = _import_folder(folder)
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        else:
            self._send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    port = 7070
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"POC server running at http://localhost:{port}")
    print("Open that URL in your browser.")
    server.serve_forever()
