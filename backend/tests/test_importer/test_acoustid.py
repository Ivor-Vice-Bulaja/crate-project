"""
test_acoustid.py — Tests for backend/importer/acoustid.py.

All network calls are mocked. No real HTTP requests in any test.

Test structure mirrors the Test Plan in md/plans/acoustid-lookup.md:
  - Core assertions
  - Success path tests
  - No-match and partial failure tests
  - Failure path tests
  - Rate limit test
"""

from unittest.mock import MagicMock, patch

import acoustid as acoustid_lib
import musicbrainzngs
import pytest


def _mock_release_response(data: dict) -> MagicMock:
    """Build a mock requests.Response whose .json() returns data."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp

from backend.config import AcoustIDConfig
from backend.importer.acoustid import identify_track

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ALL_KEYS = [
    "acoustid_id",
    "acoustid_score",
    "acoustid_match",
    "mb_recording_id",
    "mb_release_id",
    "mb_artist_id",
    "title",
    "artist",
    "artist_sort_name",
    "year",
    "mb_duration_s",
    "isrc",
    "mb_release_title",
    "release_status",
    "release_country",
    "mb_release_group_id",
    "mb_release_group_type",
    "label",
    "catalogue_number",
    "mb_has_front_art",
    "genres",
    "tags",
]


@pytest.fixture
def config():
    """AcoustIDConfig with rate limiting and label fetch disabled for speed."""
    return AcoustIDConfig(
        acoustid_api_key="test-acoustid-key",
        acoustid_timeout=10,
        mb_contact="test@example.com",
        mb_rate_limit=False,
        fetch_label=True,
    )


@pytest.fixture
def config_no_label(config):
    """AcoustIDConfig with label fetch disabled."""
    config.fetch_label = False
    return config


@pytest.fixture
def fingerprint_ok():
    """Mock acoustid.fingerprint_file returning a valid duration + fingerprint."""
    with patch("backend.importer.acoustid.acoustid.fingerprint_file") as m:
        m.return_value = (210, "FINGERPRINT_DATA")
        yield m


@pytest.fixture
def acoustid_response_full():
    """Full AcoustID response with one result linked to a recording."""
    return {
        "status": "ok",
        "results": [
            {
                "id": "acoustid-uuid-001",
                "score": 0.95,
                "recordings": [
                    {
                        "id": "mb-recording-uuid-001",
                        "releasegroups": [{"id": "rg-uuid", "title": "Test EP", "type": "EP"}],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def mb_recording_response():
    """Minimal musicbrainzngs get_recording_by_id response."""
    return {
        "recording": {
            "id": "mb-recording-uuid-001",
            "title": "Test Track",
            "length": "210000",
            "first-release-date": "2020-06-15",
            "isrc-list": ["USRC12345678"],
            "artist-credit": [
                {
                    "name": "Test Artist",
                    "joinphrase": "",
                    "artist": {
                        "id": "artist-uuid-001",
                        "name": "Test Artist",
                        "sort-name": "Artist, Test",
                    },
                }
            ],
            "release-list": [
                {
                    "id": "release-uuid-001",
                    "title": "Test EP",
                    "status": "Official",
                    "date": "2020-06-15",
                    "country": "XW",
                }
            ],
            "tag-list": [{"name": "dark"}, {"name": "industrial"}],
        }
    }


@pytest.fixture
def mb_release_response():
    """Minimal MB JSON API release response with label info and cover-art-archive."""
    return {
        "id": "release-uuid-001",
        "status": "Official",
        "date": "2020-06-15",
        "label-info": [
            {
                "label": {"name": "Test Records"},
                "catalog-number": "TEST-001",
            }
        ],
        "cover-art-archive": {"front": True, "back": False, "artwork": True, "count": 1},
    }


# ---------------------------------------------------------------------------
# Helper: patch all network calls for a full-success scenario
# ---------------------------------------------------------------------------


def _patch_full_success(
    fingerprint_ok, acoustid_response_full, mb_recording_response, mb_release_response
):
    """Context manager chain for a full-success test scenario."""
    return (
        fingerprint_ok,
        patch(
            "backend.importer.acoustid.acoustid.lookup",
            return_value=acoustid_response_full,
        ),
        patch(
            "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
            return_value=mb_recording_response,
        ),
        patch(
            "backend.importer.acoustid.requests.get",
            return_value=_mock_release_response(mb_release_response),
        ),
        patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
    )


# ---------------------------------------------------------------------------
# Core assertions
# ---------------------------------------------------------------------------


class TestCoreAssertions:
    def test_return_value_is_dict(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)
        assert isinstance(result, dict)

    def test_all_expected_keys_present(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)
        for key in ALL_KEYS:
            assert key in result, f"Missing key: {key}"

    def test_acoustid_match_is_always_bool(self, fingerprint_ok, config):
        # No-match scenario
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value={"results": []}),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)
        assert isinstance(result["acoustid_match"], bool)

    def test_no_lookup_error_on_success(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)
        assert "lookup_error" not in result

    def test_genres_and_tags_are_lists_when_mb_succeeds_empty(
        self, fingerprint_ok, acoustid_response_full, config
    ):
        """genres and tags should be [] not None when MB succeeds but returns no entries."""
        recording_no_tags = {
            "recording": {
                "id": "mb-recording-uuid-001",
                "title": "Test Track",
                "length": "210000",
                "first-release-date": "2020",
                "isrcs": [],
                "artist-credit": [
                    {
                        "name": "A",
                        "joinphrase": "",
                        "artist": {"id": "x", "name": "A", "sort-name": "A"},
                    }
                ],
                "release-list": [],
                "genres": [],
                "tags": [],
            }
        }
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=recording_no_tags,
            ),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_release_by_id",
                return_value={"release": {"label-info": []}},
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)
        assert result["genres"] == []
        assert result["tags"] == []


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_full_success_fields_populated(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["acoustid_id"] == "acoustid-uuid-001"
        assert result["acoustid_score"] == 0.95
        assert result["acoustid_match"] is True
        assert result["mb_recording_id"] == "mb-recording-uuid-001"
        assert result["title"] == "Test Track"
        assert result["artist"] == "Test Artist"
        assert result["artist_sort_name"] == "Artist, Test"
        assert result["year"] == 2020
        assert result["mb_duration_s"] == 210.0
        assert result["isrc"] == "USRC12345678"
        assert result["mb_release_id"] == "release-uuid-001"
        assert result["mb_release_title"] == "Test EP"
        assert result["release_status"] == "Official"
        assert result["release_country"] == "XW"
        assert result["mb_release_group_type"] == "EP"
        assert result["label"] == "Test Records"
        assert result["catalogue_number"] == "TEST-001"
        assert result["genres"] == []  # genres not supported by musicbrainzngs 0.7.1
        assert result["tags"] == ["dark", "industrial"]

    def test_no_releases_linked_to_recording(self, fingerprint_ok, acoustid_response_full, config):
        recording_no_releases = {
            "recording": {
                "id": "mb-recording-uuid-001",
                "title": "Test Track",
                "length": "180000",
                "first-release-date": "2019",
                "isrcs": [],
                "artist-credit": [
                    {
                        "name": "DJ X",
                        "joinphrase": "",
                        "artist": {"id": "ax", "name": "DJ X", "sort-name": "X, DJ"},
                    }
                ],
                "release-list": [],
                "genres": [],
                "tags": [],
            }
        }
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=recording_no_releases,
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["mb_release_id"] is None
        assert result["label"] is None
        assert result["catalogue_number"] is None
        assert result["title"] == "Test Track"
        assert result["artist"] == "DJ X"
        assert "lookup_error" not in result

    def test_fetch_label_false_no_second_mb_call(
        self, fingerprint_ok, acoustid_response_full, mb_recording_response, config_no_label
    ):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch("backend.importer.acoustid.requests.get") as mock_release,
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config_no_label)

        mock_release.assert_not_called()
        assert result["label"] is None
        assert result["catalogue_number"] is None
        # Other MB fields still populated
        assert result["title"] == "Test Track"

    def test_mb_rate_limit_false_no_sleep(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        """When mb_rate_limit=False, time.sleep should never be called."""
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
            patch("backend.importer.acoustid.time.sleep") as mock_sleep,
        ):
            identify_track("/fake/track.mp3", config)

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# No-match and partial failure tests
# ---------------------------------------------------------------------------


class TestNoMatchAndPartialFailure:
    def test_acoustid_empty_results(self, fingerprint_ok, config):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value={"results": []}),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["acoustid_match"] is False
        assert result["acoustid_id"] is None
        assert result["mb_recording_id"] is None
        assert "lookup_error" not in result

    def test_acoustid_result_no_recordings(self, fingerprint_ok, config):
        response = {"results": [{"id": "acoustid-uuid-002", "score": 0.88, "recordings": []}]}
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=response),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["acoustid_match"] is True
        assert result["acoustid_id"] == "acoustid-uuid-002"
        assert result["acoustid_score"] == 0.88
        assert result["mb_recording_id"] is None
        assert "lookup_error" not in result

    def test_mb_recording_404(self, fingerprint_ok, acoustid_response_full, config):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                side_effect=musicbrainzngs.ResponseError(cause=Exception("404")),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["mb_recording_id"] == "mb-recording-uuid-001"
        assert result["acoustid_id"] == "acoustid-uuid-001"
        assert result["title"] is None
        assert result["artist"] is None
        assert "lookup_error" not in result

    def test_release_lookup_raises_recording_fields_intact(
        self, fingerprint_ok, acoustid_response_full, mb_recording_response, config
    ):
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                side_effect=Exception("connection timeout"),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["label"] is None
        assert result["catalogue_number"] is None
        assert result["title"] == "Test Track"
        assert result["artist"] == "Test Artist"
        assert "lookup_error" not in result


# ---------------------------------------------------------------------------
# Failure path tests
# ---------------------------------------------------------------------------


class TestFailurePaths:
    def test_no_backend_error(self, config):
        with patch(
            "backend.importer.acoustid.acoustid.fingerprint_file",
            side_effect=acoustid_lib.NoBackendError(),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert "lookup_error" in result
        assert "fpcalc" in result["lookup_error"]
        assert result["acoustid_id"] is None
        assert result["acoustid_match"] is False

    def test_fingerprint_generation_error(self, config):
        with patch(
            "backend.importer.acoustid.acoustid.fingerprint_file",
            side_effect=acoustid_lib.FingerprintGenerationError("decode failed"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert "lookup_error" in result
        assert result["acoustid_id"] is None

    def test_web_service_error_succeeds_on_retry(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        lookup_calls = [acoustid_lib.WebServiceError("503"), acoustid_response_full]
        with (
            patch("backend.importer.acoustid.acoustid.lookup", side_effect=lookup_calls),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
            patch("backend.importer.acoustid.time.sleep"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert result["acoustid_match"] is True
        assert result["acoustid_id"] == "acoustid-uuid-001"
        assert "lookup_error" not in result

    def test_web_service_error_both_calls_fails(self, fingerprint_ok, config):
        with (
            patch(
                "backend.importer.acoustid.acoustid.lookup",
                side_effect=acoustid_lib.WebServiceError("503"),
            ),
            patch("backend.importer.acoustid.time.sleep"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert "lookup_error" in result
        assert result["acoustid_id"] is None

    def test_unexpected_exception_never_raises(self, config):
        """Outer try/except must catch anything and return a dict."""
        with patch(
            "backend.importer.acoustid.acoustid.fingerprint_file",
            side_effect=RuntimeError("something unexpected"),
        ):
            result = identify_track("/fake/track.mp3", config)

        assert isinstance(result, dict)
        assert "lookup_error" in result
        assert result["acoustid_match"] is False


# ---------------------------------------------------------------------------
# Rate limit tests
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_sleep_called_for_each_mb_call_when_rate_limit_true(
        self, fingerprint_ok, acoustid_response_full, mb_recording_response, mb_release_response
    ):
        """With mb_rate_limit=True and fetch_label=True, sleep should be called twice."""
        config = AcoustIDConfig(
            acoustid_api_key="test-key",
            mb_contact="test@example.com",
            mb_rate_limit=True,
            fetch_label=True,
        )
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
            patch("backend.importer.acoustid.time.sleep") as mock_sleep,
        ):
            identify_track("/fake/track.mp3", config)

        # One sleep before recording lookup, one before release lookup
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1)

    def test_no_sleep_when_rate_limit_false(
        self,
        fingerprint_ok,
        acoustid_response_full,
        mb_recording_response,
        mb_release_response,
        config,
    ):
        """config fixture has mb_rate_limit=False — no sleeps at all."""
        with (
            patch("backend.importer.acoustid.acoustid.lookup", return_value=acoustid_response_full),
            patch(
                "backend.importer.acoustid.musicbrainzngs.get_recording_by_id",
                return_value=mb_recording_response,
            ),
            patch(
                "backend.importer.acoustid.requests.get",
                return_value=_mock_release_response(mb_release_response),
            ),
            patch("backend.importer.acoustid.musicbrainzngs.set_useragent"),
            patch("backend.importer.acoustid.time.sleep") as mock_sleep,
        ):
            identify_track("/fake/track.mp3", config)

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# _select_best_release unit tests
# ---------------------------------------------------------------------------


class TestSelectBestRelease:
    from backend.importer.acoustid import _select_best_release

    def test_returns_none_for_empty_list(self):
        from backend.importer.acoustid import _select_best_release

        assert _select_best_release([]) is None

    def test_prefers_official_with_earliest_date(self):
        from backend.importer.acoustid import _select_best_release

        releases = [
            {"id": "a", "status": "Official", "date": "2021-01-01"},
            {"id": "b", "status": "Official", "date": "2019-06-01"},
            {"id": "c", "status": "Bootleg", "date": "2018-01-01"},
        ]
        assert _select_best_release(releases)["id"] == "b"

    def test_official_no_date_over_any_with_date(self):
        from backend.importer.acoustid import _select_best_release

        releases = [
            {"id": "a", "status": "Official"},
            {"id": "b", "status": "Bootleg", "date": "2010-01-01"},
        ]
        assert _select_best_release(releases)["id"] == "a"

    def test_any_with_date_over_any_without(self):
        from backend.importer.acoustid import _select_best_release

        releases = [
            {"id": "a", "status": "Bootleg"},
            {"id": "b", "status": "Bootleg", "date": "2015-03-01"},
        ]
        assert _select_best_release(releases)["id"] == "b"

    def test_fallback_first_release(self):
        from backend.importer.acoustid import _select_best_release

        releases = [{"id": "x"}, {"id": "y"}]
        assert _select_best_release(releases)["id"] == "x"
