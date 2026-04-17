"""
config.py — Centralised application settings.

Why centralise config?
- Every module that needs a setting imports it from one place.
- Missing or misconfigured env vars are caught immediately at startup
  with a clear error message, not buried in a stack trace three calls deep.
- Secrets never appear as string literals in the codebase.

Usage:
    from backend.config import settings

    api_key = settings.anthropic_api_key
    db_path = settings.db_path

How it works:
    python-dotenv loads the .env file into the process environment.
    Each field reads from os.environ. Fields marked as required raise
    a clear ConfigurationError if the variable is missing or empty.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root. Does nothing if .env does not exist
# (environment variables already in the shell environment take precedence).
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


class ConfigurationError(ValueError):
    """Raised when a required environment variable is missing."""


def _require(name: str) -> str:
    """
    Read a required environment variable.
    Raises ConfigurationError with a helpful message if it is missing or empty.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example to .env and fill in your values."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    """Read an optional environment variable, returning default if absent."""
    return os.environ.get(name, default).strip()


class Settings:
    """
    Application configuration. All env vars are read here.
    Import `settings` (the singleton instance below), not this class.
    """

    # --- Required keys ---
    # These raise ConfigurationError at startup if missing.
    # Comment: we access them as properties so the error only triggers
    # when actually needed — this allows tests to run without all keys set.

    @property
    def anthropic_api_key(self) -> str:
        return _require("ANTHROPIC_API_KEY")

    @property
    def acoustid_api_key(self) -> str:
        return _require("ACOUSTID_API_KEY")

    # --- Optional keys ---

    @property
    def musicbrainz_app(self) -> str:
        return _optional("MUSICBRAINZ_APP", "CrateApp/0.1")

    @property
    def discogs_token(self) -> str:
        return _optional("DISCOGS_TOKEN")

    @property
    def spotify_client_id(self) -> str:
        return _optional("SPOTIFY_CLIENT_ID")

    @property
    def spotify_client_secret(self) -> str:
        return _optional("SPOTIFY_CLIENT_SECRET")

    # --- Paths ---

    @property
    def db_path(self) -> str:
        return _optional("DB_PATH", "./crate.db")

    @property
    def music_folder(self) -> str:
        return _optional("MUSIC_FOLDER")

    # --- Runtime settings ---

    @property
    def log_level(self) -> str:
        return _optional("LOG_LEVEL", "INFO").upper()


# Singleton — import this, not the class.
settings = Settings()


@dataclass
class EssentiaConfig:
    """
    All tuneable settings for the Essentia audio analysis module.

    Pass an instance of this to analyse_track(). Nothing is hardcoded in
    essentia_analysis.py — every knob lives here.
    """

    # RhythmExtractor2013 tempo bounds (BPM). Set for techno/house ranges.
    min_tempo: int = 100
    max_tempo: int = 160

    # How many top genre label strings to store in genre_top_labels.
    genre_top_n: int = 5

    # Directory containing TensorFlow .pb model files and .json metadata files.
    model_dir: Path = field(default_factory=lambda: Path("./models"))

    # Set False to skip the entire ML section (no essentia-tensorflow needed).
    # CI and lightweight environments should leave this False.
    run_ml_models: bool = True

    # Set False to skip PredominantPitchMelodia (slow: ~10–30 s per track).
    run_pitch_analysis: bool = True


@dataclass
class AcoustIDConfig:
    """
    All tuneable settings for the AcoustID + MusicBrainz lookup module.

    Pass an instance of this to identify_track(). Every knob lives here —
    nothing is hardcoded in acoustid.py.
    """

    # AcoustID application API key. Required — obtain free at acoustid.org/api-key.
    acoustid_api_key: str = field(default_factory=lambda: _require("ACOUSTID_API_KEY"))

    # Request timeout in seconds for the AcoustID API call.
    acoustid_timeout: int = 10

    # Email or URL included in the MusicBrainz User-Agent header.
    # Required by MusicBrainz terms of service.
    mb_contact: str = field(default_factory=lambda: _require("MUSICBRAINZ_APP"))

    # Whether to sleep 1 s before each MusicBrainz call to stay within
    # the 1 req/s rate limit. Disable only in tests.
    mb_rate_limit: bool = True

    # Whether to make a second MusicBrainz call to fetch label and
    # catalogue number from the selected release. Adds ~1 s per track.
    fetch_label: bool = True


@dataclass
class DiscogsConfig:
    """
    All tuneable settings for the Discogs API enrichment module.

    Pass an instance of this to fetch_discogs_metadata(). Nothing is
    hardcoded in discogs.py — every knob lives here.
    """

    # Personal access token for Discogs API auth.
    # None → unauthenticated, rate-limited to 25 req/min.
    # Set via DISCOGS_TOKEN env var.
    discogs_token: str | None = field(default_factory=lambda: _optional("DISCOGS_TOKEN") or None)

    # User-Agent header sent with every request.
    # Required by Discogs API terms of service.
    user_agent: str = field(
        default_factory=lambda: _optional("DISCOGS_APP", "CrateApp/0.1 (user@example.com)")
    )

    # Max candidates to score per search call (per_page). Cap at 10.
    max_search_results: int = 5

    # Minimum score for "high" confidence.
    confidence_threshold_high: float = 3.0

    # Minimum score for "low" confidence. Below this → treated as no match.
    confidence_threshold_low: float = 1.0

    # Whether to make an extra API call to fetch the master release
    # (adds discogs_master_year and discogs_master_most_recent_id).
    fetch_master: bool = False

    # Whether to make an extra API call to fetch the label endpoint.
    # Deferred — defaults False; label name/catno already in release response.
    fetch_label: bool = False

    # Whether to add format=Vinyl on the first artist+title search attempt.
    # A DJ library is overwhelmingly vinyl; the filter reduces noise.
    vinyl_filter_first: bool = True


@dataclass
class ItunesConfig:
    """
    All tuneable settings for the iTunes Search API enrichment module.

    Pass an instance of this to fetch_itunes(). Nothing is hardcoded in
    itunes.py — every knob lives here.
    """

    # User-Agent header sent with all requests.
    user_agent: str = "CrateApp/0.1 (contact@example.com)"

    # Number of candidates fetched per search call (iTunes limit param).
    max_search_results: int = 5

    # Minimum total score to accept a match as "high" confidence.
    confidence_threshold: float = 0.7

    # Maximum duration difference (seconds) to accept a candidate.
    # 15s is tight enough to distinguish different mixes of the same track
    # (e.g. Original Mix at 332s vs Ojala Remix at 352s = 19.7s diff → rejected).
    duration_tolerance_seconds: float = 15.0

    # Ordered list of country codes to try after US returns zero results.
    country_fallbacks: list = field(default_factory=lambda: ["gb", "de"])

    # Whether to use the ?id= endpoint for re-lookups of stored trackId values.
    fetch_lookup: bool = True

    # Pixel size for artwork URL template substitution.
    artwork_size: int = 600

    # Inter-request delay in seconds (applied after every HTTP call).
    rate_limit_delay: float = 3.1

    # requests.get timeout in seconds.
    request_timeout: int = 10


@dataclass
class CoverArtConfig:
    """
    All tuneable settings for the Cover Art Archive lookup module.

    Pass an instance of this to fetch_cover_art(). No authentication required —
    the CAA is a public API.
    """

    # Pixel width of the stored thumbnail URL. CAA supports 250, 500, or 1200.
    thumbnail_size: int = 500

    # requests.get timeout in seconds.
    timeout: int = 5

    # User-Agent header sent with every request.
    user_agent: str = "CrateApp/0.1"
