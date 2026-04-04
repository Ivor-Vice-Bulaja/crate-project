"""
discogs.py — Discogs API metadata enrichment.

Takes structured track metadata and a configured discogs_client.Client instance,
searches the Discogs API for the best matching release, fetches the full release
record, and returns a flat dictionary of raw API fields.

Does not compute scores, derive features, or make curation decisions — stores
exactly what Discogs returns and leaves interpretation to later stages.

On any failure it returns a dict rather than raising, so the pipeline can always
write a partial result.

Usage:
    from backend.importer.discogs import fetch_discogs_metadata
    from backend.config import DiscogsConfig
    import discogs_client

    client = discogs_client.Client("CrateApp/0.1", user_token="...")
    result = fetch_discogs_metadata(
        artist="Jeff Mills",
        title="The Bells",
        catno="PM-020",
        barcode=None,
        year=1997,
        client=client,
        config=DiscogsConfig(),
    )
"""

import json
import logging
from datetime import datetime, timezone

import discogs_client
import discogs_client.exceptions

from backend.config import DiscogsConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_RELEASE_KEYS = [
    "discogs_release_id",
    "discogs_master_id",
    "discogs_confidence",
    "discogs_search_strategy",
    "discogs_url",
    "discogs_title",
    "discogs_year",
    "discogs_country",
    "discogs_released",
    "discogs_released_formatted",
    "discogs_status",
    "discogs_data_quality",
    "discogs_notes",
    "discogs_artists_sort",
    "discogs_num_for_sale",
    "discogs_lowest_price",
    "discogs_label_id",
    "discogs_label",
    "discogs_catno",
    "discogs_label_entity_type",
    "discogs_artists",
    "discogs_genres",
    "discogs_styles",
    "discogs_format_names",
    "discogs_format_descs",
    "discogs_producers",
    "discogs_remixers",
    "discogs_extraartists_raw",
    "discogs_labels_raw",
    "discogs_tracklist",
    "discogs_barcodes",
    "discogs_matrix_numbers",
    "discogs_have",
    "discogs_want",
    "discogs_rating_avg",
    "discogs_rating_count",
    "discogs_master_year",
    "discogs_master_most_recent_id",
    "discogs_master_url",
    "discogs_lookup_timestamp",
]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _no_match_dict(strategy: str = "none") -> dict:
    """Return a fully-null dict for the no-match case."""
    result = {k: None for k in _RELEASE_KEYS}
    result["discogs_confidence"] = "none"
    result["discogs_search_strategy"] = strategy
    result["discogs_lookup_timestamp"] = _now_iso()
    return result


def _failure_dict(error: str, strategy: str = "none") -> dict:
    """Return a fully-null dict with discogs_error set."""
    result = _no_match_dict(strategy)
    result["discogs_error"] = error
    return result


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------

_PRODUCER_ROLES = {"producer", "co-producer", "executive producer", "produced by"}
_REMIXER_ROLES = {"remix", "remixed by", "re-mix", "remix by"}


def _data_get(result: object, key: str, default=None):
    """
    Read a field from a search result object.

    python3-discogs-client exposes most search result fields via __getattr__
    (delegated to self.data), but 'catno' and 'format' are absent from
    __getattr__ — they must be read directly from result.data. This helper
    tries __getattr__ first, falls back to .data.get(), then returns default.
    """
    try:
        val = getattr(result, key)
        return val
    except AttributeError:
        pass
    try:
        return result.data.get(key, default)
    except Exception:
        return default


def _score_candidate(
    result: object,
    artist: str | None,
    catno: str | None,
    year: int | None,
) -> float:
    """Score a single search result object. Higher is better."""
    score = 0.0

    # Catno exact match (case-insensitive) → +3
    if catno:
        try:
            result_catno = _data_get(result, "catno")
            if result_catno and result_catno.lower() == catno.lower():
                score += 3.0
        except Exception:
            pass

    # Artist name match in result.title (case-insensitive) → +2
    if artist:
        try:
            result_title = _data_get(result, "title") or ""
            if artist.lower() in result_title.lower():
                score += 2.0
        except Exception:
            pass

    # Year scoring
    if year is not None:
        try:
            result_year_str = _data_get(result, "year")
            if result_year_str:
                result_year = int(result_year_str)
                if result_year == year:
                    score += 1.0
                elif abs(result_year - year) <= 1:
                    score += 0.5
        except Exception:
            pass

    # Format includes Vinyl → +1
    # Format includes 12" → +0.5
    try:
        fmt = _data_get(result, "format") or []
        fmt_lower = [f.lower() for f in fmt]
        if "vinyl" in fmt_lower:
            score += 1.0
        if '12"' in fmt:
            score += 0.5
    except Exception:
        pass

    # data_quality → +0.5
    try:
        dq = _data_get(result, "data_quality")
        if dq in {"Correct", "Complete and Correct"}:
            score += 0.5
    except Exception:
        pass

    # community.have > 100 → +0.25 (tiebreaker)
    try:
        have = result.community.have
        if have and have > 100:
            score += 0.25
    except Exception:
        pass

    return score


def _select_best_candidate(
    results: list,
    artist: str | None,
    catno: str | None,
    year: int | None,
) -> tuple[object | None, float]:
    """Score all candidates and return (best_result, best_score)."""
    if not results:
        return None, 0.0

    scored = [(r, _score_candidate(r, artist, catno, year)) for r in results]
    scored.sort(key=lambda x: (x[1], _safe_have(x[0])), reverse=True)
    best_result, best_score = scored[0]
    return best_result, best_score


def _safe_have(result: object) -> int:
    try:
        community = _data_get(result, "community")
        if community is None:
            return 0
        # community may be a dict (raw data) or a CommunityDetails object
        if isinstance(community, dict):
            return community.get("have") or 0
        return getattr(community, "have", 0) or 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Search strategy
# ---------------------------------------------------------------------------

def _search_catno(
    client: discogs_client.Client,
    catno: str,
    artist: str | None,
    config: DiscogsConfig,
) -> list:
    """Try catno+artist first, fall back to catno-only if zero results."""
    per_page = min(config.max_search_results, 10)

    if artist:
        try:
            results = list(
                client.search(catno=catno, artist=artist, type="release", per_page=per_page)
            )
            if results:
                return results
        except discogs_client.exceptions.HTTPError as exc:
            if _http_status(exc) == 404:
                pass
            else:
                raise

    # catno-only fallback
    results = list(client.search(catno=catno, type="release", per_page=per_page))
    return results


def _search_barcode(
    client: discogs_client.Client,
    barcode: str,
    config: DiscogsConfig,
) -> list:
    per_page = min(config.max_search_results, 10)
    return list(client.search(barcode=barcode, type="release", per_page=per_page))


def _search_artist_title(
    client: discogs_client.Client,
    artist: str,
    title: str,
    config: DiscogsConfig,
) -> list:
    per_page = min(config.max_search_results, 10)

    if config.vinyl_filter_first:
        results = list(
            client.search(
                artist=artist,
                release_title=title,
                type="release",
                format="Vinyl",
                per_page=per_page,
            )
        )
        if results:
            return results

    # Retry without format filter
    return list(
        client.search(artist=artist, release_title=title, type="release", per_page=per_page)
    )


def _http_status(exc: discogs_client.exceptions.HTTPError) -> int | None:
    """Extract the HTTP status code from an HTTPError."""
    try:
        # python3-discogs-client HTTPError stores status in .status_code or args
        if hasattr(exc, "status_code"):
            return exc.status_code
        # Fallback: parse from string representation
        msg = str(exc)
        for part in msg.split():
            if part.isdigit():
                code = int(part)
                if 100 <= code < 600:
                    return code
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _safe_get(obj: object, attr: str, default=None):
    """Attribute access that returns default on AttributeError/TypeError."""
    try:
        val = getattr(obj, attr, default)
        return val
    except Exception:
        return default


def _safe_dict_get(d: dict, key: str, default=None):
    try:
        return d.get(key, default)
    except Exception:
        return default


def _extract_artists(release: object) -> str | None:
    try:
        artists = release.artists
        names = []
        for a in artists:
            name = getattr(a, "name", None)
            if name:
                names.append(name)
        return json.dumps(names) if names else None
    except Exception as exc:
        logger.debug("discogs: failed to extract artists: %s", exc)
        return None


def _extract_labels(release: object) -> tuple[int | None, str | None, str | None, str | None, str | None]:
    """Returns (label_id, label_name, catno, entity_type, labels_raw_json)."""
    try:
        labels = release.labels
        if not labels:
            return None, None, None, None, json.dumps([])

        # Label objects do not expose all fields via __getattr__ — use .data
        primary = labels[0]
        d = primary.data if hasattr(primary, "data") else primary
        label_id = d.get("id") if isinstance(d, dict) else getattr(primary, "id", None)
        label_name = d.get("name") if isinstance(d, dict) else getattr(primary, "name", None)
        raw_catno = d.get("catno") if isinstance(d, dict) else getattr(primary, "catno", None)
        catno = raw_catno if raw_catno else None  # empty string → None
        entity_type = d.get("entity_type_name") if isinstance(d, dict) else getattr(primary, "entity_type_name", None)

        # Build raw labels list
        raw_list = []
        for lbl in labels:
            ld = lbl.data if hasattr(lbl, "data") else lbl
            if isinstance(ld, dict):
                raw_list.append({
                    "id": ld.get("id"),
                    "name": ld.get("name"),
                    "catno": ld.get("catno"),
                    "entity_type_name": ld.get("entity_type_name"),
                })
            else:
                raw_list.append({
                    "id": getattr(lbl, "id", None),
                    "name": getattr(lbl, "name", None),
                    "catno": getattr(lbl, "catno", None),
                    "entity_type_name": getattr(lbl, "entity_type_name", None),
                })
        labels_raw = json.dumps(raw_list)

        return label_id, label_name, catno, entity_type, labels_raw
    except Exception as exc:
        logger.debug("discogs: failed to extract labels: %s", exc)
        return None, None, None, None, None


def _extract_extraartists(
    release: object,
) -> tuple[str | None, str | None, str | None]:
    """Returns (producers_json, remixers_json, extraartists_raw_json).

    extraartists is not exposed via Release.__getattr__ — read from .data.
    Items are plain dicts, not model objects.
    """
    try:
        try:
            extraartists = release.extraartists
        except AttributeError:
            extraartists = release.data.get("extraartists", []) if hasattr(release, "data") else []
        if not extraartists:
            return json.dumps([]), json.dumps([]), json.dumps([])

        producers = []
        remixers = []
        raw_list = []

        for ea in extraartists:
            # Items are plain dicts in the real API; MagicMocks in tests
            if isinstance(ea, dict):
                name = ea.get("name")
                role = ea.get("role") or ""
            else:
                name = getattr(ea, "name", None)
                role = getattr(ea, "role", "") or ""
            raw_list.append({"name": name, "role": role})

            role_lower = role.lower()
            if any(r in role_lower for r in _PRODUCER_ROLES):
                if name:
                    producers.append(name)
            if any(r in role_lower for r in _REMIXER_ROLES):
                if name:
                    remixers.append(name)

        return json.dumps(producers), json.dumps(remixers), json.dumps(raw_list)
    except Exception as exc:
        logger.debug("discogs: failed to extract extraartists: %s", exc)
        return None, None, None


def _extract_formats(release: object) -> tuple[str | None, str | None]:
    """Returns (format_names_json, format_descs_json)."""
    try:
        formats = release.formats
        if not formats:
            return json.dumps([]), json.dumps([])

        names = []
        descs = []
        for fmt in formats:
            name = fmt.get("name") if isinstance(fmt, dict) else getattr(fmt, "name", None)
            if name and name not in names:
                names.append(name)
            descriptions = (
                fmt.get("descriptions", [])
                if isinstance(fmt, dict)
                else getattr(fmt, "descriptions", []) or []
            )
            descs.extend(descriptions)

        return json.dumps(names), json.dumps(descs)
    except Exception as exc:
        logger.debug("discogs: failed to extract formats: %s", exc)
        return None, None


def _extract_tracklist(release: object) -> str | None:
    try:
        tracklist = release.tracklist
        if tracklist is None:
            return json.dumps([])

        tracks = []
        for track in tracklist:
            # type_ is not exposed via Track.__getattr__ — read from .data
            if isinstance(track, dict):
                type_ = track.get("type_", "track")
                position = track.get("position")
                title = track.get("title")
                duration = track.get("duration")
            else:
                data = track.data if hasattr(track, "data") else {}
                type_ = data.get("type_") if isinstance(data, dict) else getattr(track, "type_", "track")
                position = getattr(track, "position", None)
                title = getattr(track, "title", None)
                duration = getattr(track, "duration", None)
            if type_ != "track":
                continue
            tracks.append({
                "position": position,
                "title": title,
                "duration": duration,
                "type_": type_,
            })
        return json.dumps(tracks)
    except Exception as exc:
        logger.debug("discogs: failed to extract tracklist: %s", exc)
        return None


def _extract_identifiers(release: object) -> tuple[str | None, str | None]:
    """Returns (barcodes_json, matrix_numbers_json).

    identifiers is not exposed via Release.__getattr__ — read from .data.
    Items are plain dicts, not model objects.
    """
    try:
        try:
            identifiers = release.identifiers
        except AttributeError:
            identifiers = release.data.get("identifiers", []) if hasattr(release, "data") else []

        barcodes = []
        matrix = []
        for ident in identifiers:
            if isinstance(ident, dict):
                type_ = ident.get("type")
                value = ident.get("value")
            else:
                type_ = getattr(ident, "type", None)
                value = getattr(ident, "value", None)
            if type_ == "Barcode" and value:
                barcodes.append(value)
            elif type_ == "Matrix / Runout" and value:
                matrix.append(value)
        return json.dumps(barcodes), json.dumps(matrix)
    except Exception as exc:
        logger.debug("discogs: failed to extract identifiers: %s", exc)
        return None, None


def _extract_community(release: object) -> tuple[int | None, int | None, float | None, int | None]:
    """Returns (have, want, rating_avg, rating_count)."""
    try:
        community = release.community
        have = getattr(community, "have", None)
        want = getattr(community, "want", None)
        rating = getattr(community, "rating", None)
        rating_avg = getattr(rating, "average", None) if rating else None
        rating_count = getattr(rating, "count", None) if rating else None
        return have, want, rating_avg, rating_count
    except Exception as exc:
        logger.debug("discogs: failed to extract community: %s", exc)
        return None, None, None, None


# ---------------------------------------------------------------------------
# Full release extraction
# ---------------------------------------------------------------------------

def _extract_release(release: object) -> dict:
    """Extract all fields from a full release object into the output dict."""
    result: dict = {}

    # Scalars — use _data_get so fields absent from __getattr__ are still read.
    # Wrapped individually so one failure doesn't abort everything.
    for attr, key in [
        ("id", "discogs_release_id"),
        ("title", "discogs_title"),
        ("year", "discogs_year"),
        ("country", "discogs_country"),
        ("released", "discogs_released"),
        ("released_formatted", "discogs_released_formatted"),
        ("status", "discogs_status"),
        ("data_quality", "discogs_data_quality"),
        ("artists_sort", "discogs_artists_sort"),
        ("notes", "discogs_notes"),
        ("num_for_sale", "discogs_num_for_sale"),
        ("lowest_price", "discogs_lowest_price"),
        ("uri", "discogs_url"),
        ("master_url", "discogs_master_url"),
    ]:
        try:
            result[key] = _data_get(release, attr)
        except Exception as exc:
            logger.debug("discogs: failed to extract field %s: %s", key, exc)
            result[key] = None

    # master_id — treat 0 and absent as None
    try:
        raw_master_id = _data_get(release, "master_id")
        result["discogs_master_id"] = raw_master_id if raw_master_id else None
    except Exception as exc:
        logger.debug("discogs: failed to extract discogs_master_id: %s", exc)
        result["discogs_master_id"] = None

    # Complex fields
    result["discogs_artists"] = _extract_artists(release)

    label_id, label_name, catno, entity_type, labels_raw = _extract_labels(release)
    result["discogs_label_id"] = label_id
    result["discogs_label"] = label_name
    result["discogs_catno"] = catno
    result["discogs_label_entity_type"] = entity_type
    result["discogs_labels_raw"] = labels_raw

    producers, remixers, extraartists_raw = _extract_extraartists(release)
    result["discogs_producers"] = producers
    result["discogs_remixers"] = remixers
    result["discogs_extraartists_raw"] = extraartists_raw

    format_names, format_descs = _extract_formats(release)
    result["discogs_format_names"] = format_names
    result["discogs_format_descs"] = format_descs

    try:
        genres = getattr(release, "genres", None)
        result["discogs_genres"] = json.dumps(genres if genres is not None else [])
    except Exception as exc:
        logger.debug("discogs: failed to extract genres: %s", exc)
        result["discogs_genres"] = json.dumps([])

    try:
        styles = getattr(release, "styles", None)
        result["discogs_styles"] = json.dumps(styles if styles is not None else [])
    except Exception as exc:
        logger.debug("discogs: failed to extract styles: %s", exc)
        result["discogs_styles"] = json.dumps([])

    result["discogs_tracklist"] = _extract_tracklist(release)

    barcodes, matrix_numbers = _extract_identifiers(release)
    result["discogs_barcodes"] = barcodes
    result["discogs_matrix_numbers"] = matrix_numbers

    have, want, rating_avg, rating_count = _extract_community(release)
    result["discogs_have"] = have
    result["discogs_want"] = want
    result["discogs_rating_avg"] = rating_avg
    result["discogs_rating_count"] = rating_count

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_discogs_metadata(
    artist: str | None,
    title: str | None,
    catno: str | None,
    barcode: str | None,
    year: int | None,
    client: discogs_client.Client,
    config: DiscogsConfig,
) -> dict:
    """
    Search Discogs for the best matching release and return a flat metadata dict.

    Never raises — all exceptions are caught and returned as a failure dict with
    discogs_error set. See module docstring for return contract by outcome.
    """
    strategy = "none"
    try:
        results: list = []

        # --- Step 1: catno ---
        if catno:
            strategy = "catno"
            try:
                results = _search_catno(client, catno, artist, config)
            except discogs_client.exceptions.HTTPError as exc:
                status = _http_status(exc)
                if status == 404:
                    logger.debug("discogs: catno search 404 for catno=%s", catno)
                elif status and 400 <= status < 500:
                    logger.warning("discogs: catno search HTTP %s: %s", status, exc)
                    return _failure_dict(str(exc), strategy)
                else:
                    logger.warning("discogs: catno search HTTP %s: %s", status, exc)
                    return _failure_dict(str(exc), strategy)

        # --- Step 2: barcode ---
        if not results and barcode:
            strategy = "barcode"
            try:
                results = _search_barcode(client, barcode, config)
            except discogs_client.exceptions.HTTPError as exc:
                status = _http_status(exc)
                if status == 404:
                    logger.debug("discogs: barcode search 404 for barcode=%s", barcode)
                elif status and 400 <= status < 500:
                    logger.warning("discogs: barcode search HTTP %s: %s", status, exc)
                    return _failure_dict(str(exc), strategy)
                else:
                    logger.warning("discogs: barcode search HTTP %s: %s", status, exc)
                    return _failure_dict(str(exc), strategy)

        # --- Step 3: artist + title ---
        if not results and artist and title:
            strategy = "artist_title"
            try:
                results = _search_artist_title(client, artist, title, config)
            except discogs_client.exceptions.HTTPError as exc:
                status = _http_status(exc)
                if status == 404:
                    logger.debug("discogs: artist+title search 404")
                elif status and 400 <= status < 500:
                    logger.warning("discogs: artist+title search HTTP %s: %s", status, exc)
                    return _failure_dict(str(exc), strategy)
                else:
                    logger.warning("discogs: artist+title search HTTP %s: %s", status, exc)
                    return _failure_dict(str(exc), strategy)

        # --- Step 4: no results after all strategies ---
        if not results:
            logger.debug(
                "discogs: no results for artist=%s title=%s catno=%s barcode=%s",
                artist, title, catno, barcode,
            )
            return _no_match_dict("none")

        # --- Candidate selection ---
        best_result, best_score = _select_best_candidate(results, artist, catno, year)

        if best_result is None or best_score < config.confidence_threshold_low:
            logger.debug(
                "discogs: best score %.2f below threshold for artist=%s catno=%s",
                best_score, artist, catno,
            )
            return _no_match_dict("none")

        confidence = (
            "high" if best_score >= config.confidence_threshold_high else "low"
        )

        if confidence == "low":
            logger.info(
                "discogs: low-confidence match (score=%.2f) for artist=%s catno=%s → release_id=%s",
                best_score, artist, catno, getattr(best_result, "id", None),
            )
        else:
            logger.debug(
                "discogs: high-confidence match (score=%.2f) strategy=%s release_id=%s",
                best_score, strategy, getattr(best_result, "id", None),
            )

        release_id = getattr(best_result, "id", None)

        # --- Fetch full release ---
        try:
            release = client.release(release_id)
        except discogs_client.exceptions.HTTPError as exc:
            status = _http_status(exc)
            if status == 404:
                logger.debug("discogs: release %s not found (404)", release_id)
                return _failure_dict(str(exc), strategy)
            elif status and 400 <= status < 500:
                logger.warning("discogs: release fetch HTTP %s: %s", status, exc)
                return _failure_dict(str(exc), strategy)
            else:
                logger.warning("discogs: release fetch HTTP %s: %s", status, exc)
                return _failure_dict(str(exc), strategy)

        # --- Extract all fields ---
        result = _extract_release(release)
        result["discogs_confidence"] = confidence
        result["discogs_search_strategy"] = strategy
        result["discogs_lookup_timestamp"] = _now_iso()

        # --- Optional master fetch ---
        master_id = result.get("discogs_master_id")
        if config.fetch_master and master_id:
            try:
                master = client.master(master_id)
                result["discogs_master_year"] = _data_get(master, "year")
                result["discogs_master_most_recent_id"] = _data_get(
                    master, "most_recent_release"
                )
            except Exception as exc:
                logger.debug("discogs: master fetch failed for master_id=%s: %s", master_id, exc)
                result["discogs_master_year"] = None
                result["discogs_master_most_recent_id"] = None
        else:
            result.setdefault("discogs_master_year", None)
            result.setdefault("discogs_master_most_recent_id", None)

        # Ensure every schema key is present (guard against extraction gaps)
        for key in _RELEASE_KEYS:
            result.setdefault(key, None)

        return result

    except discogs_client.exceptions.TooManyAttemptsError:
        logger.warning("discogs: rate limit max retries exceeded")
        return _failure_dict("rate limit: max retries exceeded", strategy)

    except discogs_client.exceptions.AuthorizationError as exc:
        logger.error("discogs: authorization error (check DISCOGS_TOKEN): %s", exc)
        return _failure_dict(str(exc), strategy)

    except discogs_client.exceptions.ConfigurationError as exc:
        logger.error("discogs: configuration error: %s", exc)
        return _failure_dict(str(exc), strategy)

    except Exception as exc:
        logger.error("discogs: unexpected error: %s", exc, exc_info=True)
        return _failure_dict(str(exc), strategy)
