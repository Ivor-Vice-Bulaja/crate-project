"""
acoustid.py — AcoustID fingerprinting and MusicBrainz metadata lookup.

Takes a file path and returns a flat dict of identification and metadata fields.
Does not compute derived scores, select crate membership, or write to the database.

On any failure it returns a dict rather than raising, so the pipeline can always
write a partial result. See the return contract in the plan doc for exact field
semantics by failure mode.

Usage:
    from backend.importer.acoustid import identify_track
    from backend.config import AcoustIDConfig

    result = identify_track("/path/to/track.mp3", AcoustIDConfig())
"""

import logging
import time

import acoustid
import musicbrainzngs
import requests

from backend.config import AcoustIDConfig

logger = logging.getLogger(__name__)

# Guard against calling set_useragent more than once per process.
_mb_useragent_set = False


def _ensure_mb_useragent(config: AcoustIDConfig) -> None:
    """Call musicbrainzngs.set_useragent once per process."""
    global _mb_useragent_set
    if not _mb_useragent_set:
        # Contact is typically "AppName/version (email)" per MB requirements.
        musicbrainzngs.set_useragent("CrateApp", "0.1", config.mb_contact)
        _mb_useragent_set = True


def _null_result(lookup_error: str | None = None) -> dict:
    """Return a fully-null dict, optionally with a lookup_error key."""
    result = {
        "acoustid_id": None,
        "acoustid_score": None,
        "acoustid_match": False,
        "mb_recording_id": None,
        "mb_release_id": None,
        "mb_artist_id": None,
        "title": None,
        "artist": None,
        "artist_sort_name": None,
        "year": None,
        "mb_duration_s": None,
        "isrc": None,
        "mb_release_title": None,
        "release_status": None,
        "release_country": None,
        "mb_release_group_id": None,
        "mb_release_group_type": None,
        "label": None,
        "catalogue_number": None,
        "mb_has_front_art": None,
        "genres": None,
        "tags": None,
    }
    if lookup_error is not None:
        result["lookup_error"] = lookup_error
    return result


def _select_best_release(releases: list) -> dict | None:
    """
    Pick a single release from the recording's release list for label/catalogue lookup.

    Priority order:
    1. Official releases with a date — earliest by lexicographic date string.
    2. Official releases without a date — first one.
    3. Any release with a date — earliest.
    4. Any release — first.
    5. Empty list — None.
    """
    if not releases:
        return None

    official_with_date = [r for r in releases if r.get("status") == "Official" and r.get("date")]
    if official_with_date:
        return min(official_with_date, key=lambda r: r["date"])

    official_no_date = [r for r in releases if r.get("status") == "Official"]
    if official_no_date:
        return official_no_date[0]

    with_date = [r for r in releases if r.get("date")]
    if with_date:
        return min(with_date, key=lambda r: r["date"])

    return releases[0]


def identify_track(file_path: str, config: AcoustIDConfig) -> dict:
    """
    Fingerprint an audio file and return identification + metadata fields.

    Parameters
    ----------
    file_path : str
        Absolute path to the audio file.
    config : AcoustIDConfig
        Tuneable settings — API keys, timeouts, feature flags.

    Returns
    -------
    dict
        Flat dict of all output fields. Never raises. See plan doc for full
        schema and per-failure-mode field values.
    """
    try:
        return _identify_track_inner(file_path, config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error in identify_track for %s: %s", file_path, exc)
        return _null_result(lookup_error=str(exc))


def _identify_track_inner(file_path: str, config: AcoustIDConfig) -> dict:
    # --- Fingerprinting ---
    try:
        duration, fingerprint = acoustid.fingerprint_file(file_path)
    except acoustid.NoBackendError:
        return _null_result(lookup_error="fpcalc and Chromaprint library not found")
    except acoustid.FingerprintGenerationError as exc:
        return _null_result(lookup_error=str(exc))

    # --- AcoustID lookup (retry once on WebServiceError) ---
    try:
        response = acoustid.lookup(
            apikey=config.acoustid_api_key,
            fingerprint=fingerprint,
            duration=int(duration),
            meta=["recordings", "releasegroups"],
            timeout=config.acoustid_timeout,
        )
    except acoustid.WebServiceError:
        time.sleep(2)
        try:
            response = acoustid.lookup(
                apikey=config.acoustid_api_key,
                fingerprint=fingerprint,
                duration=int(duration),
                meta=["recordings", "releasegroups"],
                timeout=config.acoustid_timeout,
            )
        except acoustid.WebServiceError as exc:
            return _null_result(lookup_error=str(exc))

    # --- No match ---
    results = response.get("results", [])
    if not results:
        result = _null_result()
        result["acoustid_match"] = False
        return result

    # --- Extract best result ---
    best = max(results, key=lambda r: r["score"])
    acoustid_id = best["id"]
    acoustid_score = best["score"]

    recordings = best.get("recordings", [])
    if not recordings:
        # Fingerprint found but not linked to any MusicBrainz recording.
        result = _null_result()
        result["acoustid_match"] = True
        result["acoustid_id"] = acoustid_id
        result["acoustid_score"] = acoustid_score
        return result

    recording_stub = recordings[0]
    mb_recording_id = recording_stub.get("id")

    # Extract release group ID and type from the AcoustID recording stub if present.
    rgs = recording_stub.get("releasegroups", [])
    mb_release_group_id = rgs[0].get("id") if rgs else None
    mb_release_group_type = rgs[0].get("type") if rgs else None

    # --- MusicBrainz recording lookup ---
    _ensure_mb_useragent(config)

    if config.mb_rate_limit:
        time.sleep(1)

    mb_fields = _fetch_mb_recording(mb_recording_id, config)

    # --- Assemble final result ---
    result = {
        "acoustid_id": acoustid_id,
        "acoustid_score": acoustid_score,
        "acoustid_match": True,
        "mb_recording_id": mb_recording_id,
        "mb_release_group_id": mb_release_group_id,
        "mb_release_group_type": mb_release_group_type,
        **mb_fields,
    }
    return result


def _fetch_mb_recording(mb_recording_id: str, config: AcoustIDConfig) -> dict:
    """
    Fetch a MusicBrainz recording and return all metadata fields.
    Returns nulled fields (not lookup_error) on any failure.
    """
    null_mb = {
        "mb_release_id": None,
        "mb_artist_id": None,
        "title": None,
        "artist": None,
        "artist_sort_name": None,
        "year": None,
        "mb_duration_s": None,
        "isrc": None,
        "mb_release_title": None,
        "release_status": None,
        "release_country": None,
        "label": None,
        "catalogue_number": None,
        "genres": None,
        "tags": None,
    }

    try:
        result = musicbrainzngs.get_recording_by_id(
            mb_recording_id,
            includes=["artist-credits", "releases", "isrcs", "tags"],
        )
    except musicbrainzngs.ResponseError:
        # 404 — recording deleted or merged; store the ID but null the metadata.
        logger.warning("MusicBrainz recording %s not found (404)", mb_recording_id)
        return null_mb
    except musicbrainzngs.NetworkError:
        time.sleep(3)
        try:
            result = musicbrainzngs.get_recording_by_id(
                mb_recording_id,
                includes=["artist-credits", "releases", "isrcs", "tags"],
            )
        except musicbrainzngs.NetworkError as exc:
            logger.warning("MusicBrainz network error for %s after retry: %s", mb_recording_id, exc)
            return null_mb
    except Exception as exc:  # noqa: BLE001
        logger.warning("MusicBrainz unexpected error for %s: %s", mb_recording_id, exc)
        return null_mb

    recording = result["recording"]

    # Title
    title = recording.get("title")

    # Duration (MB returns milliseconds; convert to seconds)
    length_ms = recording.get("length")
    mb_duration_s = round(int(length_ms) / 1000, 3) if length_ms else None

    # First release year
    first_date = recording.get("first-release-date", "")
    year = int(first_date[:4]) if first_date and len(first_date) >= 4 else None

    # Artist (assembled from credits array with join phrases).
    # Each credit entry has an "artist" sub-object with the name; "name" at the
    # top level is only present when the credited name differs from the canonical name.
    credits = recording.get("artist-credit", [])
    artist = (
        "".join(
            c.get("name", c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
            for c in credits
            if isinstance(c, dict)
        ).strip()
        or None
    )

    # Artist MBID and sort name from first credited artist
    mb_artist_id = None
    artist_sort_name = None
    if credits and isinstance(credits[0], dict):
        artist_obj = credits[0].get("artist", {})
        mb_artist_id = artist_obj.get("id")
        artist_sort_name = artist_obj.get("sort-name")

    # ISRC (first one only) — musicbrainzngs returns "isrc-list", not "isrcs"
    isrcs = recording.get("isrc-list", [])
    isrc = isrcs[0] if isrcs else None

    # Tags — musicbrainzngs returns "tag-list", not "tags"
    # genres is not supported by musicbrainzngs 0.7.1 so always []
    genres = []
    tags = [t["name"] for t in recording.get("tag-list", [])]

    # Select best release — musicbrainzngs returns "release-list", not "releases"
    releases = recording.get("release-list", [])
    best_release = _select_best_release(releases)
    mb_release_id = best_release["id"] if best_release else None
    mb_release_title = best_release.get("title") if best_release else None
    release_country = best_release.get("country") if best_release else None
    release_status = best_release.get("status") if best_release else None

    # Label / catalogue number — optional second MB call
    label = None
    catalogue_number = None
    mb_has_front_art = None
    if config.fetch_label and mb_release_id:
        if config.mb_rate_limit:
            time.sleep(1)
        label, catalogue_number, release_status_from_lookup, year_from_lookup, mb_has_front_art = (
            _fetch_release_label(mb_release_id)
        )
        # Prefer release lookup values — they are more reliably populated than
        # the embedded release stub returned inside the recording response.
        if release_status_from_lookup is not None:
            release_status = release_status_from_lookup
        if year_from_lookup is not None:
            year = year_from_lookup

    return {
        "mb_release_id": mb_release_id,
        "mb_artist_id": mb_artist_id,
        "title": title,
        "artist": artist,
        "artist_sort_name": artist_sort_name,
        "year": year,
        "mb_duration_s": mb_duration_s,
        "isrc": isrc,
        "mb_release_title": mb_release_title,
        "release_status": release_status,
        "release_country": release_country,
        "label": label,
        "catalogue_number": catalogue_number,
        "mb_has_front_art": mb_has_front_art,
        "genres": genres,
        "tags": tags,
    }


def _fetch_release_label(
    mb_release_id: str,
) -> tuple[str | None, str | None, str | None, int | None, bool | None]:
    """
    Fetch label, catalogue number, release status, year, and cover art flag
    from a MusicBrainz release.
    Returns (None, None, None, None, None) on any failure.

    Uses a raw JSON request rather than musicbrainzngs for this call because
    musicbrainzngs 0.7.1 does not include "cover-art-archive" in its validated
    includes list, even though the MB API supports it.

    Key names from the MB JSON API:
    - "label-info" array (JSON) vs "label-info-list" (musicbrainzngs XML)
    - "catalog-number" (American spelling)
    - "cover-art-archive.front" is a boolean
    """
    url = f"https://musicbrainz.org/ws/2/release/{mb_release_id}"
    params = {"inc": "labels", "fmt": "json"}
    headers = {"User-Agent": musicbrainzngs.musicbrainz._useragent}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        release = resp.json()

        label_info = release.get("label-info", [])
        if label_info:
            label = label_info[0].get("label", {}).get("name")
            catalogue_number = label_info[0].get("catalog-number")
        else:
            label = None
            catalogue_number = None

        status = release.get("status")

        date = release.get("date", "")
        year = int(date[:4]) if date and len(date) >= 4 else None

        caa = release.get("cover-art-archive", {})
        front = caa.get("front")
        mb_has_front_art = bool(front) if front is not None else None

        return label, catalogue_number, status, year, mb_has_front_art
    except Exception as exc:  # noqa: BLE001
        logger.warning("Release label lookup failed for %s: %s", mb_release_id, exc)
        return None, None, None, None, None
