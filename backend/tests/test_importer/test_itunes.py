"""
Tests for backend/importer/itunes.py.

All HTTP calls are mocked — no live API calls are made.
requests.get is patched at backend.importer.itunes.requests.Session.
"""

from unittest.mock import MagicMock, call, patch

import requests

from backend.config import ItunesConfig
from backend.importer.itunes import fetch_itunes

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MOCK_TRACK = {
    "wrapperType": "track",
    "kind": "song",
    "trackId": 123456,
    "artistId": 111,
    "collectionId": 222,
    "trackName": "The Bells",
    "artistName": "Jeff Mills",
    "collectionName": "The Bells EP",
    "releaseDate": "1996-01-01T00:00:00Z",
    "trackTimeMillis": 252000,  # 252 s
    "discCount": 1,
    "discNumber": 1,
    "trackCount": 4,
    "trackNumber": 1,
    "primaryGenreName": "Electronic",
    "trackExplicitness": "notExplicit",
    "isStreamable": True,
    "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/Music/abc/100x100bb.jpg",
    "trackViewUrl": "https://music.apple.com/us/album/the-bells/222?i=123456",
    "artistViewUrl": "https://music.apple.com/us/artist/jeff-mills/111",
    "collectionViewUrl": "https://music.apple.com/us/album/the-bells-ep/222",
}


def _mock_response(results=None, status_code=200):
    """Return a mock requests.Response-like object."""
    if results is None:
        results = [MOCK_TRACK]
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = {"resultCount": len(results), "results": results}
    mock.url = "https://itunes.apple.com/search"
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        http_err = requests.HTTPError(response=mock)
        mock.raise_for_status.side_effect = http_err
    return mock


def _config(**kwargs) -> ItunesConfig:
    """Return an ItunesConfig with rate_limit_delay=0 for fast tests."""
    defaults = {"rate_limit_delay": 0, "request_timeout": 5}
    defaults.update(kwargs)
    return ItunesConfig(**defaults)


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_single_result_extracted(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.return_value = _mock_response()

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())

    assert result["itunes_track_id"] == 123456
    assert result["itunes_artist_id"] == 111
    assert result["itunes_collection_id"] == 222
    assert result["itunes_track_name"] == "The Bells"
    assert result["itunes_artist_name"] == "Jeff Mills"
    assert result["itunes_collection_name"] == "The Bells EP"
    assert result["itunes_release_date"] == "1996-01-01T00:00:00Z"
    assert result["itunes_track_time_ms"] == 252000
    assert result["itunes_genre"] == "Electronic"
    assert result["itunes_track_explicit"] == "notExplicit"
    assert result["itunes_is_streamable"] is True
    assert result["itunes_confidence"] == "high"
    assert result["itunes_search_strategy"] == "artist_title"
    assert result["itunes_country"] == "us"
    assert result["itunes_error"] is None


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_multiple_results_best_score_selected(mock_session, mock_sleep):
    """Three candidates; the one with matching duration should win."""
    candidate_match = dict(MOCK_TRACK, trackTimeMillis=252000)  # matches 252s
    candidate_long = dict(MOCK_TRACK, trackId=999, trackTimeMillis=600000)  # 600s — rejected
    candidate_short = dict(MOCK_TRACK, trackId=888, trackTimeMillis=120000)  # 120s — rejected

    session = mock_session.return_value
    session.get.return_value = _mock_response(
        results=[candidate_long, candidate_short, candidate_match]
    )

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_track_id"] == 123456


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_duration_within_threshold_accepted(mock_session, mock_sleep):
    candidate = dict(MOCK_TRACK, trackTimeMillis=262000)  # 262s, diff=10s < 15s
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[candidate])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] in ("high", "low")
    assert result["itunes_track_id"] == 123456


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_duration_outside_threshold_rejected(mock_session, mock_sleep):
    """Single candidate with duration > 30s off → no match."""
    candidate = dict(MOCK_TRACK, trackTimeMillis=120000)  # 120s, diff=132s
    session = mock_session.return_value
    # All three countries return the rejected candidate
    session.get.return_value = _mock_response(results=[candidate])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config(country_fallbacks=[]))
    assert result["itunes_confidence"] == "none"
    assert result["itunes_track_id"] is None


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_preview_url_not_stored(mock_session, mock_sleep):
    """previewUrl in the API response must never appear in the output dict."""
    track_with_preview = dict(
        MOCK_TRACK, previewUrl="https://audio-ssl.itunes.apple.com/preview.m4a"
    )
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[track_with_preview])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert "previewUrl" not in result
    assert "itunes_preview_url" not in result


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_artwork_url_transformed(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.return_value = _mock_response()

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config(artwork_size=600))
    assert result["itunes_artwork_url"] == (
        "https://is1-ssl.mzstatic.com/image/thumb/Music/abc/600x600bb.jpg"
    )


# ---------------------------------------------------------------------------
# Country fallback tests
# ---------------------------------------------------------------------------


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_us_zero_results_falls_back_to_gb(mock_session, mock_sleep):
    session = mock_session.return_value
    us_empty = _mock_response(results=[])
    gb_result = _mock_response(results=[MOCK_TRACK])
    session.get.side_effect = [us_empty, gb_result]

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config(country_fallbacks=["gb"]))
    assert result["itunes_country"] == "gb"
    assert result["itunes_search_strategy"] == "artist_title"
    assert result["itunes_confidence"] in ("high", "low")


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_all_countries_zero_results(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config(country_fallbacks=["gb", "de"]))
    assert result["itunes_confidence"] == "none"
    assert result["itunes_search_strategy"] == "none"
    assert session.get.call_count == 3  # us + gb + de


# ---------------------------------------------------------------------------
# Failure path tests
# ---------------------------------------------------------------------------


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_http_403_backoff_retry_success(mock_session, mock_sleep):
    session = mock_session.return_value
    resp_403 = _mock_response(status_code=403)
    resp_ok = _mock_response()
    session.get.side_effect = [resp_403, resp_ok]

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] == "high"
    # sleep called once for rate_limit_delay (=0 in config) + once for 60s backoff
    assert any(c == call(60) for c in mock_sleep.call_args_list)


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_http_403_backoff_retry_still_403(mock_session, mock_sleep):
    session = mock_session.return_value
    resp_403 = _mock_response(status_code=403)
    session.get.return_value = resp_403

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] == "none"
    assert "rate_limit" in result["itunes_error"]


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_http_5xx_retries_then_error_dict(mock_session, mock_sleep):
    session = mock_session.return_value
    resp_503 = _mock_response(status_code=503)
    session.get.return_value = resp_503

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] == "none"
    assert "server_error" in result["itunes_error"]
    # 1 initial + 3 retries (each calls _do_request which calls session.get)
    assert session.get.call_count >= 4


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_http_400_no_retry(mock_session, mock_sleep):
    session = mock_session.return_value
    resp_400 = _mock_response(status_code=400)
    session.get.return_value = resp_400

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] == "none"
    assert "bad_request" in result["itunes_error"]
    assert session.get.call_count == 1


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_timeout_returns_error_dict(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.side_effect = requests.exceptions.Timeout()

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] == "none"
    assert "timeout" in result["itunes_error"]


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_unknown_exception_top_level_fallback(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.side_effect = ValueError("unexpected")

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_confidence"] == "none"
    assert "unexpected" in result["itunes_error"]
    assert "ValueError" in result["itunes_error"]


# ---------------------------------------------------------------------------
# Field extraction tests
# ---------------------------------------------------------------------------


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_compilation_fields_stored(mock_session, mock_sleep):
    va_track = dict(
        MOCK_TRACK,
        collectionArtistId=999,
        collectionArtistName="Various Artists",
    )
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[va_track])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_collection_artist_id"] == 999
    assert result["itunes_collection_artist_name"] == "Various Artists"


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_compilation_fields_absent(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[MOCK_TRACK])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_collection_artist_id"] is None
    assert result["itunes_collection_artist_name"] is None


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_is_streamable_stored_as_bool(mock_session, mock_sleep):
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[MOCK_TRACK])

    result = fetch_itunes("Jeff Mills", "The Bells", 252.0, _config())
    assert result["itunes_is_streamable"] is True
    assert isinstance(result["itunes_is_streamable"], bool)


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_lookup_by_id_path(mock_session, mock_sleep):
    """Re-lookup by stored trackId should call the lookup endpoint, not search."""
    session = mock_session.return_value
    session.get.return_value = _mock_response()

    result = fetch_itunes(
        "Jeff Mills",
        "The Bells",
        252.0,
        _config(fetch_lookup=True),
        stored_track_id=123456,
    )

    assert result["itunes_search_strategy"] == "id"
    assert result["itunes_confidence"] == "high"
    # Must have called the lookup URL, not the search URL
    call_url = session.get.call_args[0][0]
    assert "lookup" in call_url
    assert "search" not in call_url


@patch("backend.importer.itunes.time.sleep")
@patch("backend.importer.itunes.requests.Session")
def test_no_duration_disables_rejection(mock_session, mock_sleep):
    """With duration_seconds=None, candidates must not be rejected for duration."""
    # Candidate with a wildly different trackTimeMillis — would be rejected if duration scoring active
    candidate = dict(MOCK_TRACK, trackTimeMillis=10000)  # 10s
    session = mock_session.return_value
    session.get.return_value = _mock_response(results=[candidate])

    result = fetch_itunes("Jeff Mills", "The Bells", None, _config())
    # Should NOT return no-match; candidate was not rejected
    assert result["itunes_track_id"] == 123456
    assert result["itunes_confidence"] in ("high", "low")
