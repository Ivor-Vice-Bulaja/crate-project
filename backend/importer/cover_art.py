"""
cover_art.py — Cover Art Archive lookup for a MusicBrainz release or release group.

Returns a flat dict with the resolved cover art URL and lookup metadata.
Never raises — all errors are returned as structured data so the pipeline
can always write a partial result.

Lookup strategy (two-step fallback):
  1. Release-level: GET /release/{mbid}/front-{size}
  2. Release-group fallback: GET /release-group/{mbid}/front-{size}

The CAA returns a 307 redirect to the actual image on archive.org. We store
the canonical coverartarchive.org request URL rather than the Location header,
because the archive.org path is an internal implementation detail that can
change if CAA reorganises storage or merges MBIDs. The frontend follows the
redirect at display time.
"""

import logging
import time
from datetime import datetime, timezone

import requests

from backend.config import CoverArtConfig

logger = logging.getLogger(__name__)

_CAA_BASE = "https://coverartarchive.org"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _no_art_dict() -> dict:
    return {
        "cover_art_url": None,
        "cover_art_source": None,
        "cover_art_lookup_timestamp": _now_iso(),
    }


def _get(url: str, config: CoverArtConfig) -> requests.Response:
    return requests.get(
        url,
        allow_redirects=False,
        timeout=config.timeout,
        headers={"User-Agent": config.user_agent},
    )


def _get_with_503_retry(url: str, config: CoverArtConfig) -> requests.Response:
    resp = _get(url, config)
    if resp.status_code == 503:
        logger.warning("CAA 503 for %s — retrying once after 1 s", url)
        time.sleep(1)
        resp = _get(url, config)
    return resp


def fetch_cover_art(
    release_mbid: str | None,
    release_group_mbid: str | None,
    config: CoverArtConfig,
    mb_has_front_art: bool | None = None,
) -> dict:
    """
    Fetch a cover art URL from the Cover Art Archive.

    Parameters
    ----------
    release_mbid:
        MusicBrainz release MBID (from AcoustID/MB pipeline). May be None.
    release_group_mbid:
        MusicBrainz release-group MBID. May be None.
    config:
        Tuneable settings (thumbnail size, timeout, user-agent).
    mb_has_front_art:
        Pre-check flag from the MusicBrainz release response field
        ``cover-art-archive.front``.
        True  → definitely has art (still attempt the call).
        False → skip the release-level CAA call.
        None  → unknown; attempt the call.

    Returns
    -------
    dict
        Always contains ``cover_art_url``, ``cover_art_source``, and
        ``cover_art_lookup_timestamp``. ``cover_art_error`` is added only on
        network or unexpected failures (not on clean 404s).
    """
    try:
        # --- Early exit: nothing to look up ---
        if release_mbid is None and release_group_mbid is None:
            return _no_art_dict()

        if mb_has_front_art is False and release_group_mbid is None:
            return _no_art_dict()

        cover_art_error: str | None = None

        # --- Step 1: Release-level lookup ---
        if mb_has_front_art is not False and release_mbid is not None:
            url = f"{_CAA_BASE}/release/{release_mbid}/front-{config.thumbnail_size}"
            try:
                resp = _get_with_503_retry(url, config)
                if resp.status_code == 307:
                    return {
                        "cover_art_url": url,
                        "cover_art_source": "release",
                        "cover_art_lookup_timestamp": _now_iso(),
                    }
                elif resp.status_code == 404:
                    pass  # expected — fall through to release-group
                elif resp.status_code == 400:
                    logger.error(
                        "CAA 400 Bad Request for release MBID %s — invalid UUID (caller bug)",
                        release_mbid,
                    )
                else:
                    logger.warning(
                        "CAA unexpected status %d for release %s",
                        resp.status_code,
                        release_mbid,
                    )
            except requests.RequestException as exc:
                logger.warning(
                    "CAA network error for release %s: %s", release_mbid, exc
                )
                cover_art_error = str(exc)
                # fall through to release-group step

        # --- Step 2: Release-group fallback ---
        if release_group_mbid is None:
            result = _no_art_dict()
            if cover_art_error:
                result["cover_art_error"] = cover_art_error
            return result

        url = f"{_CAA_BASE}/release-group/{release_group_mbid}/front-{config.thumbnail_size}"
        try:
            resp = _get_with_503_retry(url, config)
            if resp.status_code == 307:
                result = {
                    "cover_art_url": url,
                    "cover_art_source": "release_group",
                    "cover_art_lookup_timestamp": _now_iso(),
                }
                if cover_art_error:
                    result["cover_art_error"] = cover_art_error
                return result
            elif resp.status_code == 404:
                result = _no_art_dict()
                if cover_art_error:
                    result["cover_art_error"] = cover_art_error
                return result
            elif resp.status_code == 400:
                logger.error(
                    "CAA 400 Bad Request for release-group MBID %s — invalid UUID (caller bug)",
                    release_group_mbid,
                )
                result = _no_art_dict()
                if cover_art_error:
                    result["cover_art_error"] = cover_art_error
                return result
            else:
                msg = f"Unexpected CAA status {resp.status_code} for release-group {release_group_mbid}"
                logger.warning(msg)
                result = _no_art_dict()
                result["cover_art_error"] = msg
                return result
        except requests.RequestException as exc:
            logger.warning(
                "CAA network error for release-group %s: %s", release_group_mbid, exc
            )
            result = _no_art_dict()
            result["cover_art_error"] = str(exc)
            return result

    except Exception as exc:
        logger.error("Unexpected error in fetch_cover_art: %s", exc, exc_info=True)
        result = _no_art_dict()
        result["cover_art_error"] = str(exc)
        return result
