"""
itunes.py — iTunes Search API metadata enrichment.

Takes a track's known metadata (artist, title, duration) and returns a flat
dictionary of raw iTunes Search API fields ready to be written to SQLite.

Does not score, rank, or derive any application-level values — it stores what
iTunes returns and lets downstream stages decide what to do with it.

iTunes is optional enrichment. Its primary value is artwork URLs and day-precision
release dates. It does not provide label, catalogue number, ISRC, BPM, or key.

On any failure it returns a dict rather than raising, so the pipeline can always
write a partial result.

Usage:
    from backend.importer.itunes import fetch_itunes
    from backend.config import ItunesConfig

    result = fetch_itunes(
        artist="Jeff Mills",
        title="The Bells",
        duration_seconds=252.4,
        config=ItunesConfig(),
    )
"""

import logging
import re
import time
from datetime import UTC, datetime

import requests
from rapidfuzz import fuzz

from backend.config import ItunesConfig

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://itunes.apple.com/search"
_LOOKUP_URL = "https://itunes.apple.com/lookup"

# Extracts the content of the last parenthesised group in a title string,
# used to detect mix/remix descriptors like "(Original Mix)" or "(Kolter Remix)".
_MIX_DESCRIPTOR_RE = re.compile(r"\(([^)]+)\)\s*$")


# ---------------------------------------------------------------------------
# Null / error dict builders
# ---------------------------------------------------------------------------


def _null_dict() -> dict:
    """Return an all-None dict with all itunes_* keys present."""
    return {
        "itunes_track_id": None,
        "itunes_artist_id": None,
        "itunes_collection_id": None,
        "itunes_confidence": "none",
        "itunes_track_name": None,
        "itunes_artist_name": None,
        "itunes_collection_name": None,
        "itunes_release_date": None,
        "itunes_track_time_ms": None,
        "itunes_disc_count": None,
        "itunes_disc_number": None,
        "itunes_track_count": None,
        "itunes_track_number": None,
        "itunes_genre": None,
        "itunes_track_explicit": None,
        "itunes_is_streamable": None,
        "itunes_artwork_url": None,
        "itunes_track_url": None,
        "itunes_artist_url": None,
        "itunes_collection_url": None,
        "itunes_collection_artist_id": None,
        "itunes_collection_artist_name": None,
        "itunes_search_strategy": "none",
        "itunes_country": "none",
        "itunes_lookup_timestamp": _utc_now(),
        "itunes_error": None,
    }


def _error_dict(error_msg: str) -> dict:
    d = _null_dict()
    d["itunes_lookup_timestamp"] = _utc_now()
    d["itunes_error"] = error_msg
    return d


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _get(session: requests.Session, url: str, params: dict, config: ItunesConfig) -> dict:
    """
    Make a GET request, apply rate-limit delay, handle 403/429 (60s backoff, 1 retry)
    and 5xx (exponential backoff, 3 retries).

    Returns the parsed JSON dict on success.
    Raises requests.HTTPError or requests.exceptions.Timeout on unrecoverable failure.
    """
    headers = {"User-Agent": config.user_agent}

    def _do_request() -> requests.Response:
        resp = session.get(url, params=params, headers=headers, timeout=config.request_timeout)
        time.sleep(config.rate_limit_delay)
        return resp

    # --- First attempt ---
    resp = _do_request()

    # 403 / 429 — backoff 60s, one retry
    if resp.status_code in (403, 429):
        logger.warning(
            "iTunes rate limit (%s) on %s — sleeping 60s then retrying", resp.status_code, resp.url
        )
        time.sleep(60)
        resp = _do_request()
        if resp.status_code in (403, 429):
            resp.raise_for_status()

    # 400 — code bug, do not retry
    if resp.status_code == 400:
        logger.error("iTunes HTTP 400 on %s — check request parameters", resp.url)
        resp.raise_for_status()

    # 5xx — exponential backoff, 3 retries
    if resp.status_code >= 500:
        delays = [1, 2, 4]
        for delay in delays:
            logger.warning(
                "iTunes HTTP %s on %s — retrying in %ss", resp.status_code, resp.url, delay
            )
            time.sleep(delay)
            resp = _do_request()
            if resp.status_code < 500:
                break
        else:
            resp.raise_for_status()

    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Artwork URL transformation
# ---------------------------------------------------------------------------

_ARTWORK_RE = re.compile(r"/\d+x\d+bb\.jpg$")


def _transform_artwork_url(raw_url: str | None, size: int) -> str | None:
    if not raw_url:
        return None
    transformed = _ARTWORK_RE.sub(f"/{size}x{size}bb.jpg", raw_url)
    # If the regex didn't match (unexpected URL format), return None
    if transformed == raw_url and not raw_url.endswith(f"/{size}x{size}bb.jpg"):
        return None
    return transformed


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------


def _score_candidate(
    result: dict,
    artist: str,
    title: str,
    duration_seconds: float | None,
    config: ItunesConfig,
) -> float | None:
    """
    Score a single iTunes result candidate against known artist/title/duration.

    Returns a float score in [0.0, 1.0], or None if the candidate is rejected
    by duration check.

    If duration_seconds is None, duration scoring is omitted and max score is 0.8.
    """
    # Validate result type
    if result.get("wrapperType") != "track" or result.get("kind") != "song":
        return None

    # Mix-variant rejection: if the query title has a mix descriptor
    # (contains "mix", "remix", "edit", "dub", "version", "instrumental")
    # and the candidate's last parenthetical is also a mix descriptor,
    # reject if they are clearly different (fuzzy ratio < 60).
    # Only fires when the query has an explicit mix name — avoids false
    # rejections when the candidate's parenthetical is a feat. credit.
    mix_words_re = re.compile(
        r"\b(mix|remix|edit|dub|version|instrumental|rework|bootleg)\b",
        re.IGNORECASE,
    )
    query_mix_m = _MIX_DESCRIPTOR_RE.search(title)
    if query_mix_m and mix_words_re.search(query_mix_m.group(1)):
        candidate_mix_m = _MIX_DESCRIPTOR_RE.search(result.get("trackName", ""))
        if candidate_mix_m and mix_words_re.search(candidate_mix_m.group(1)):
            mix_similarity = fuzz.ratio(
                query_mix_m.group(1).lower(), candidate_mix_m.group(1).lower()
            )
            if mix_similarity < 60:
                return None  # different mix variant — reject

    # Duration rejection
    if duration_seconds is not None:
        track_time_ms = result.get("trackTimeMillis")
        if track_time_ms is not None:
            diff = abs(track_time_ms / 1000.0 - duration_seconds)
            if diff > config.duration_tolerance_seconds:
                return None  # rejected
            duration_score = 0.2
        else:
            duration_score = 0.0
    else:
        duration_score = 0.0

    artist_score = fuzz.token_sort_ratio(result.get("artistName", ""), artist) / 100.0 * 0.4

    title_score = fuzz.token_sort_ratio(result.get("trackName", ""), title) / 100.0 * 0.4

    return artist_score + title_score + duration_score


# ---------------------------------------------------------------------------
# Field extractor
# ---------------------------------------------------------------------------


def _extract_fields(
    result: dict,
    strategy: str,
    country: str,
    config: ItunesConfig,
) -> dict:
    """Map an iTunes result object to the itunes_-prefixed output dict."""
    d = _null_dict()
    d["itunes_track_id"] = result.get("trackId")
    d["itunes_artist_id"] = result.get("artistId")
    d["itunes_collection_id"] = result.get("collectionId")
    d["itunes_track_name"] = result.get("trackName")
    d["itunes_artist_name"] = result.get("artistName")
    d["itunes_collection_name"] = result.get("collectionName")
    d["itunes_release_date"] = result.get("releaseDate")
    d["itunes_track_time_ms"] = result.get("trackTimeMillis")
    d["itunes_disc_count"] = result.get("discCount")
    d["itunes_disc_number"] = result.get("discNumber")
    d["itunes_track_count"] = result.get("trackCount")
    d["itunes_track_number"] = result.get("trackNumber")
    d["itunes_genre"] = result.get("primaryGenreName")
    d["itunes_track_explicit"] = result.get("trackExplicitness")
    d["itunes_is_streamable"] = result.get("isStreamable")
    d["itunes_artwork_url"] = _transform_artwork_url(
        result.get("artworkUrl100"), config.artwork_size
    )
    d["itunes_track_url"] = result.get("trackViewUrl")
    d["itunes_artist_url"] = result.get("artistViewUrl")
    d["itunes_collection_url"] = result.get("collectionViewUrl")
    d["itunes_collection_artist_id"] = result.get("collectionArtistId")
    d["itunes_collection_artist_name"] = result.get("collectionArtistName")
    d["itunes_search_strategy"] = strategy
    d["itunes_country"] = country
    d["itunes_lookup_timestamp"] = _utc_now()
    d["itunes_error"] = None
    return d


# ---------------------------------------------------------------------------
# Best candidate selection
# ---------------------------------------------------------------------------


def _select_best(
    results: list[dict],
    artist: str,
    title: str,
    duration_seconds: float | None,
    config: ItunesConfig,
) -> tuple[dict | None, float]:
    """
    Score all candidates and return (best_result, best_score).
    Returns (None, 0.0) if all candidates are rejected or results is empty.
    """
    best_result = None
    best_score = 0.0

    for result in results:
        score = _score_candidate(result, artist, title, duration_seconds, config)
        if score is None:
            continue  # duration-rejected
        if score > best_score:
            best_score = score
            best_result = result

    return best_result, best_score


# ---------------------------------------------------------------------------
# Search strategy loop
# ---------------------------------------------------------------------------


def _search(
    session: requests.Session,
    artist: str,
    title: str,
    duration_seconds: float | None,
    config: ItunesConfig,
) -> dict | None:
    """
    Run the search strategy loop (us → country fallbacks).

    Returns a completed itunes_* dict on success, or None if no match found.
    Raises on HTTP errors (caller handles).
    """
    countries = ["us"] + list(config.country_fallbacks)

    for country in countries:
        params = {
            "term": f"{artist} {title}",
            "media": "music",
            "entity": "song",
            "country": country,
            "limit": config.max_search_results,
        }
        data = _get(session, _SEARCH_URL, params, config)
        results = data.get("results", [])

        if not results:
            continue  # try next country

        best_result, best_score = _select_best(results, artist, title, duration_seconds, config)

        if best_result is None or best_score == 0.0:
            # All candidates rejected — try next country
            continue

        d = _extract_fields(best_result, "artist_title", country, config)
        if best_score >= config.confidence_threshold:
            d["itunes_confidence"] = "high"
        else:
            d["itunes_confidence"] = "low"
        return d

    return None  # no match across all countries


# ---------------------------------------------------------------------------
# Lookup by stored trackId
# ---------------------------------------------------------------------------


def _lookup_by_id(
    session: requests.Session,
    track_id: int,
    config: ItunesConfig,
) -> dict | None:
    """
    Fetch a track by its stored iTunes trackId.

    Returns a completed itunes_* dict on success, or None if not found.
    Raises on HTTP errors (caller handles).
    """
    params = {"id": track_id}
    data = _get(session, _LOOKUP_URL, params, config)
    results = data.get("results", [])

    if not results:
        return None

    result = results[0]
    # For lookup-by-id we don't score — the ID match is authoritative
    d = _extract_fields(result, "id", "us", config)
    d["itunes_confidence"] = "high"
    return d


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_itunes(
    artist: str,
    title: str,
    duration_seconds: float | None,
    config: ItunesConfig,
    stored_track_id: int | None = None,
) -> dict:
    """
    Look up a track on the iTunes Search API and return a flat dict of
    itunes_-prefixed fields.

    Always returns a dict — never raises. See module docstring for return
    contract by outcome.

    Args:
        artist: Known artist name (from MusicBrainz or file tags).
        title: Known track title.
        duration_seconds: File duration from mutagen (seconds); None disables
            duration scoring and rejection.
        config: ItunesConfig dataclass with all tunable parameters.
        stored_track_id: Stored iTunes trackId for re-lookup path; None for
            fresh imports.
    """
    try:
        session = requests.Session()

        # Step 1: re-lookup by stored ID
        if config.fetch_lookup and stored_track_id is not None:
            result = _lookup_by_id(session, stored_track_id, config)
            if result is not None:
                return result
            # ID not found — fall through to no-match (do not fall back to search)
            return _null_dict()

        # Step 2–4: keyword search with country fallbacks
        result = _search(session, artist, title, duration_seconds, config)
        if result is not None:
            return result

        # No match
        return _null_dict()

    except requests.exceptions.Timeout:
        logger.warning("iTunes request timed out for artist=%r title=%r", artist, title)
        return _error_dict("timeout: request timed out")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        if status in (403, 429):
            return _error_dict(f"rate_limit: HTTP {status} after retry")
        if status == 400:
            return _error_dict("bad_request: HTTP 400 — check request parameters")
        if isinstance(status, int) and status >= 500:
            return _error_dict(f"server_error: HTTP {status} after 3 retries")
        return _error_dict(f"http_error: HTTP {status}")

    except Exception as e:
        logger.error("iTunes unexpected error for artist=%r title=%r: %r", artist, title, e)
        return _error_dict(f"unexpected: {type(e).__name__}: {e}")
