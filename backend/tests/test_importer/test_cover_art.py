"""
Tests for backend.importer.cover_art.fetch_cover_art.

All HTTP calls are mocked — no real network requests.
"""

import unittest
from unittest.mock import MagicMock, patch, call

from backend.config import CoverArtConfig
from backend.importer.cover_art import fetch_cover_art

RELEASE_MBID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
RG_MBID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CONFIG = CoverArtConfig(thumbnail_size=500, timeout=5, user_agent="TestApp/0.1")

EXPECTED_RELEASE_URL = f"https://coverartarchive.org/release/{RELEASE_MBID}/front-500"
EXPECTED_RG_URL = f"https://coverartarchive.org/release-group/{RG_MBID}/front-500"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def mock_307(location: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 307
    resp.headers = {"Location": location}
    return resp


def mock_404() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 404
    return resp


def mock_status(code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = code
    return resp


# ---------------------------------------------------------------------------
# Helper to assert always-present schema keys
# ---------------------------------------------------------------------------

def assert_schema(result: dict) -> None:
    assert isinstance(result, dict), "result must be a dict"
    assert "cover_art_url" in result
    assert "cover_art_source" in result
    assert "cover_art_lookup_timestamp" in result
    assert result["cover_art_lookup_timestamp"], "timestamp must be non-empty"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchCoverArt(unittest.TestCase):

    @patch("backend.importer.cover_art.requests.get")
    def test_release_hit(self, mock_get):
        mock_get.return_value = mock_307("unused")

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] == EXPECTED_RELEASE_URL
        assert result["cover_art_source"] == "release"
        assert "cover_art_error" not in result

    @patch("backend.importer.cover_art.requests.get")
    def test_release_miss_release_group_hit(self, mock_get):
        mock_get.side_effect = [mock_404(), mock_307("unused")]

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] == EXPECTED_RG_URL
        assert result["cover_art_source"] == "release_group"
        assert "cover_art_error" not in result
        assert mock_get.call_count == 2

    @patch("backend.importer.cover_art.requests.get")
    def test_both_miss(self, mock_get):
        mock_get.side_effect = [mock_404(), mock_404()]

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] is None
        assert result["cover_art_source"] is None
        assert "cover_art_error" not in result

    @patch("backend.importer.cover_art.requests.get")
    def test_precheck_skip_release_group_hit(self, mock_get):
        """mb_has_front_art=False skips release call; release-group is still attempted."""
        mock_get.return_value = mock_307("unused")

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG, mb_has_front_art=False)

        assert_schema(result)
        assert result["cover_art_source"] == "release_group"
        assert result["cover_art_url"] == EXPECTED_RG_URL
        assert mock_get.call_count == 1
        # Confirm the single call targeted release-group, not release
        called_url = mock_get.call_args[0][0]
        assert "release-group" in called_url

    @patch("backend.importer.cover_art.requests.get")
    def test_precheck_skip_no_release_group_mbid(self, mock_get):
        """mb_has_front_art=False with no release-group MBID → no requests."""
        result = fetch_cover_art(RELEASE_MBID, None, CONFIG, mb_has_front_art=False)

        assert_schema(result)
        assert result["cover_art_url"] is None
        mock_get.assert_not_called()

    @patch("backend.importer.cover_art.requests.get")
    def test_both_mbids_none(self, mock_get):
        result = fetch_cover_art(None, None, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] is None
        mock_get.assert_not_called()

    @patch("backend.importer.cover_art.requests.get")
    def test_network_error_on_release_still_attempts_release_group(self, mock_get):
        import requests as req
        mock_get.side_effect = [req.RequestException("timeout"), mock_307("unused")]

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] == EXPECTED_RG_URL
        assert result["cover_art_source"] == "release_group"
        assert "cover_art_error" in result  # error from release step carried through

    @patch("backend.importer.cover_art.requests.get")
    def test_network_error_on_both_calls(self, mock_get):
        import requests as req
        mock_get.side_effect = [req.RequestException("timeout"), req.RequestException("timeout")]

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] is None
        assert "cover_art_error" in result

    @patch("backend.importer.cover_art.requests.get")
    def test_timestamp_always_set(self, mock_get):
        mock_get.return_value = mock_404()

        for scenario_fn in [
            lambda: fetch_cover_art(None, None, CONFIG),
            lambda: fetch_cover_art(RELEASE_MBID, None, CONFIG, mb_has_front_art=False),
            lambda: fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG),
        ]:
            result = scenario_fn()
            assert result["cover_art_lookup_timestamp"], "timestamp must always be set"

    @patch("backend.importer.cover_art.requests.get")
    def test_never_raises(self, mock_get):
        """Function must not raise regardless of what the mock does."""
        mock_get.side_effect = Exception("unexpected boom")

        result = fetch_cover_art(RELEASE_MBID, RG_MBID, CONFIG)

        assert isinstance(result, dict)
        assert "cover_art_error" in result

    @patch("backend.importer.cover_art.requests.get")
    def test_release_only_no_release_group(self, mock_get):
        """Release hit with no release-group MBID returns release-level art."""
        mock_get.return_value = mock_307("unused")

        result = fetch_cover_art(RELEASE_MBID, None, CONFIG)

        assert result["cover_art_url"] == EXPECTED_RELEASE_URL
        assert result["cover_art_source"] == "release"

    @patch("backend.importer.cover_art.requests.get")
    def test_release_404_no_release_group_returns_no_art(self, mock_get):
        """Release 404 with no release-group MBID → no art, no error."""
        mock_get.return_value = mock_404()

        result = fetch_cover_art(RELEASE_MBID, None, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] is None
        assert "cover_art_error" not in result

    @patch("backend.importer.cover_art.requests.get")
    def test_400_on_release_no_cover_art_error(self, mock_get):
        """400 Bad Request is a caller bug — logged at ERROR but no cover_art_error."""
        mock_get.return_value = mock_status(400)

        result = fetch_cover_art(RELEASE_MBID, None, CONFIG)

        assert_schema(result)
        assert result["cover_art_url"] is None
        assert "cover_art_error" not in result


if __name__ == "__main__":
    unittest.main()
