"""
test_discogs.py — Tests for backend/importer/discogs.py.

All Discogs HTTP calls are mocked. No live API calls are made in any test.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.config import DiscogsConfig
from backend.importer.discogs import fetch_discogs_metadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> DiscogsConfig:
    return DiscogsConfig(
        discogs_token="test-token",
        user_agent="TestApp/1.0",
        max_search_results=5,
        confidence_threshold_high=3.0,
        confidence_threshold_low=1.0,
        fetch_master=False,
        fetch_label=False,
        vinyl_filter_first=True,
    )


@pytest.fixture()
def mock_search_result() -> MagicMock:
    result = MagicMock()
    result.id = 616407
    result.title = "Jeff Mills - The Bells (10th Anniversary)"
    result.catno = "PM-020"
    result.year = "2006"
    result.format = ["Vinyl", '12"', "33 \u2153 RPM"]
    result.data_quality = "Correct"
    result.master_id = 449968
    result.master_url = "https://api.discogs.com/masters/449968"
    result.community = MagicMock(have=1423, want=2246)
    return result


@pytest.fixture()
def mock_release() -> MagicMock:
    release = MagicMock()
    release.id = 616407
    release.title = "The Bells (10th Anniversary)"
    release.year = 2006
    release.country = "US"
    release.released = "2006-00-00"
    release.released_formatted = "2006"
    release.status = "Accepted"
    release.data_quality = "Correct"
    release.master_id = 449968
    release.master_url = "https://api.discogs.com/masters/449968"
    release.uri = "/release/616407-Jeff-Mills-The-Bells-10th-Anniversary"
    release.artists_sort = "Mills, Jeff"
    release.notes = ""
    release.num_for_sale = 10
    release.lowest_price = 25.0

    artist_mock = MagicMock()
    artist_mock.name = "Jeff Mills"
    artist_mock.join = ""
    release.artists = [artist_mock]

    label_mock = MagicMock()
    label_mock.id = 123
    label_mock.name = "Purpose Maker"
    label_mock.catno = "PM-020"
    label_mock.entity_type_name = "Label"
    release.labels = [label_mock]

    release.genres = ["Electronic"]
    release.styles = ["Techno", "Tribal"]
    release.formats = [{"name": "Vinyl", "qty": "1", "descriptions": ['12"', "33 \u2153 RPM"]}]
    release.extraartists = []

    track_mock = MagicMock()
    track_mock.position = "A"
    track_mock.title = "The Bells"
    track_mock.duration = "9:05"
    track_mock.type_ = "track"
    release.tracklist = [track_mock]

    ident_mock = MagicMock()
    ident_mock.type = "Barcode"
    ident_mock.value = "PM 020-A"
    release.identifiers = [ident_mock]

    release.community = MagicMock(
        have=1423, want=2246, rating=MagicMock(average=4.2, count=88)
    )
    return release


def _make_client(search_results=None, release=None, master=None) -> MagicMock:
    """Build a mock discogs_client.Client."""
    client = MagicMock()
    client.search.return_value = search_results if search_results is not None else []
    if release is not None:
        client.release.return_value = release
    if master is not None:
        client.master.return_value = master
    return client


# ---------------------------------------------------------------------------
# Happy path — catno match
# ---------------------------------------------------------------------------


def test_catno_match_high_confidence(config, mock_search_result, mock_release):
    client = _make_client(search_results=[mock_search_result], release=mock_release)

    result = fetch_discogs_metadata(
        artist="Jeff Mills",
        title="The Bells",
        catno="PM-020",
        barcode=None,
        year=2006,
        client=client,
        config=config,
    )

    assert result["discogs_release_id"] == 616407
    assert result["discogs_confidence"] == "high"
    assert result["discogs_search_strategy"] == "catno"
    assert result["discogs_label"] == "Purpose Maker"
    assert result["discogs_catno"] == "PM-020"
    assert result["discogs_styles"] == '["Techno", "Tribal"]'
    assert result["discogs_lookup_timestamp"] is not None
    assert "discogs_error" not in result


def test_catno_match_populates_all_keys(config, mock_search_result, mock_release):
    from backend.importer.discogs import _RELEASE_KEYS

    client = _make_client(search_results=[mock_search_result], release=mock_release)
    result = fetch_discogs_metadata(
        artist="Jeff Mills", title=None, catno="PM-020",
        barcode=None, year=None, client=client, config=config,
    )
    for key in _RELEASE_KEYS:
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Happy path — barcode fallback
# ---------------------------------------------------------------------------


def test_barcode_fallback(config, mock_search_result, mock_release):
    # catno search returns empty; barcode returns a result
    call_count = {"n": 0}
    def search_side_effect(**kwargs):
        call_count["n"] += 1
        if "catno" in kwargs:
            return []
        if "barcode" in kwargs:
            return [mock_search_result]
        return []

    client = MagicMock()
    client.search.side_effect = search_side_effect
    client.release.return_value = mock_release

    result = fetch_discogs_metadata(
        artist=None, title=None, catno="XXXXXX", barcode="PM020",
        year=None, client=client, config=config,
    )

    assert result["discogs_search_strategy"] == "barcode"
    assert result["discogs_confidence"] in ("high", "low")


# ---------------------------------------------------------------------------
# Happy path — artist+title fallback with vinyl retry
# ---------------------------------------------------------------------------


def test_artist_title_fallback_vinyl_retry(config, mock_search_result, mock_release):
    search_calls = []

    def search_side_effect(**kwargs):
        search_calls.append(kwargs)
        # First call is vinyl-filtered → empty; second call returns result
        if "format" in kwargs:
            return []
        return [mock_search_result]

    client = MagicMock()
    client.search.side_effect = search_side_effect
    client.release.return_value = mock_release

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno=None,
        barcode=None, year=2006, client=client, config=config,
    )

    assert result["discogs_search_strategy"] == "artist_title"
    # Vinyl-filtered call happened first
    assert any("format" in c for c in search_calls)
    assert result["discogs_confidence"] in ("high", "low")


# ---------------------------------------------------------------------------
# Candidate scoring — multiple results
# ---------------------------------------------------------------------------


def test_multiple_candidates_highest_score_wins(config, mock_release):
    # Candidate A: catno exact match → score ≥ 3.0
    candidate_a = MagicMock()
    candidate_a.id = 616407
    candidate_a.title = "Jeff Mills - The Bells"
    candidate_a.catno = "PM-020"
    candidate_a.year = "2006"
    candidate_a.format = ["Vinyl"]
    candidate_a.data_quality = "Correct"
    candidate_a.community = MagicMock(have=1000, want=500)

    # Candidate B: no catno match
    candidate_b = MagicMock()
    candidate_b.id = 999999
    candidate_b.title = "Some Other Release"
    candidate_b.catno = "XYZ-001"
    candidate_b.year = "1999"
    candidate_b.format = []
    candidate_b.data_quality = "Unknown"
    candidate_b.community = MagicMock(have=5, want=2)

    client = _make_client(search_results=[candidate_b, candidate_a], release=mock_release)

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    # The release fetched should be the high-scoring candidate_a
    client.release.assert_called_once_with(616407)
    assert result["discogs_confidence"] == "high"


# ---------------------------------------------------------------------------
# Low-confidence match
# ---------------------------------------------------------------------------


def test_low_confidence_match(config, mock_release):
    # Artist partial match only → score ~2.0, below high threshold
    candidate = MagicMock()
    candidate.id = 616407
    candidate.title = "Jeff Mills - Unknown Track"
    candidate.catno = "DIFFERENT-001"  # no catno match
    candidate.year = "1990"            # no year match
    candidate.format = []
    candidate.data_quality = "Unknown"
    candidate.community = MagicMock(have=5, want=2)

    client = _make_client(search_results=[candidate], release=mock_release)

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="Unknown Track", catno=None,
        barcode=None, year=None, client=client, config=config,
    )

    assert result["discogs_confidence"] == "low"
    # Data is populated even for low-confidence matches
    assert result["discogs_release_id"] is not None
    assert "discogs_error" not in result


# ---------------------------------------------------------------------------
# No match — all strategies exhausted
# ---------------------------------------------------------------------------


def test_no_match_all_strategies_exhausted(config):
    client = _make_client(search_results=[])

    result = fetch_discogs_metadata(
        artist="Unknown Artist", title="Unknown Track", catno=None,
        barcode=None, year=None, client=client, config=config,
    )

    assert result["discogs_confidence"] == "none"
    assert result["discogs_search_strategy"] == "none"
    assert result["discogs_release_id"] is None
    assert "discogs_error" not in result
    assert result["discogs_lookup_timestamp"] is not None


def test_no_inputs_returns_no_match(config):
    client = _make_client(search_results=[])

    result = fetch_discogs_metadata(
        artist=None, title=None, catno=None,
        barcode=None, year=None, client=client, config=config,
    )

    assert result["discogs_confidence"] == "none"
    assert result["discogs_search_strategy"] == "none"
    client.search.assert_not_called()


# ---------------------------------------------------------------------------
# Score below threshold — single irrelevant result
# ---------------------------------------------------------------------------


def test_single_result_below_threshold_treated_as_no_match(config):
    # No catno match, no artist in title, year very far off → score 0
    irrelevant = MagicMock()
    irrelevant.id = 1
    irrelevant.title = "Completely Unrelated"
    irrelevant.catno = "ABC-999"
    irrelevant.year = "1970"
    irrelevant.format = []
    irrelevant.data_quality = "Unknown"
    irrelevant.community = MagicMock(have=1, want=0)

    client = _make_client(search_results=[irrelevant])

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    # catno does not match → +0, year very far → +0, no artist in title → +0
    # Wait — artist "Jeff Mills" IS in "Completely Unrelated"? No. Let's check the
    # catno: "PM-020" != "ABC-999" → 0. artist "Jeff Mills" in "Completely Unrelated"? No → 0.
    # year 2006 vs 1970 → diff 36 → 0. format=[] → 0. data_quality Unknown → 0. have=1 → 0.
    # Total score = 0 → treated as no match.
    assert result["discogs_confidence"] == "none"
    assert result["discogs_release_id"] is None


# ---------------------------------------------------------------------------
# Field extraction — extraartists filtering
# ---------------------------------------------------------------------------


def test_extraartists_role_filtering(config, mock_search_result):
    producer_mock = MagicMock()
    producer_mock.name = "Producer X"
    producer_mock.role = "Producer"

    designer_mock = MagicMock()
    designer_mock.name = "Designer Y"
    designer_mock.role = "Design"

    remixer_mock = MagicMock()
    remixer_mock.name = "Remixer Z"
    remixer_mock.role = "Remixed By"

    release = MagicMock()
    release.id = 616407
    release.extraartists = [producer_mock, designer_mock, remixer_mock]
    # Set required scalar attrs
    for attr in ["title", "year", "country", "released", "released_formatted", "status",
                 "data_quality", "artists_sort", "notes", "num_for_sale", "lowest_price",
                 "uri", "master_url", "master_id", "genres", "styles", "formats",
                 "artists", "labels", "tracklist", "identifiers"]:
        setattr(release, attr, None if attr not in ("genres", "styles", "formats",
                                                      "artists", "labels", "tracklist",
                                                      "identifiers", "extraartists") else [])
    release.genres = []
    release.styles = []
    release.formats = []
    release.artists = []
    release.labels = []
    release.tracklist = []
    release.identifiers = []
    release.extraartists = [producer_mock, designer_mock, remixer_mock]
    release.community = MagicMock(have=100, want=50, rating=MagicMock(average=4.0, count=10))

    client = _make_client(search_results=[mock_search_result], release=release)

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    producers = json.loads(result["discogs_producers"])
    remixers = json.loads(result["discogs_remixers"])
    assert producers == ["Producer X"]
    assert "Designer Y" not in producers
    assert remixers == ["Remixer Z"]


# ---------------------------------------------------------------------------
# Field extraction — format_descs merging
# ---------------------------------------------------------------------------


def test_format_descs_flat_merge(config, mock_search_result, mock_release):
    mock_release.formats = [
        {"name": "Vinyl", "descriptions": ['12"', "33 \u2153 RPM"]},
        {"name": "Vinyl", "descriptions": ["Promo"]},
    ]

    client = _make_client(search_results=[mock_search_result], release=mock_release)
    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    descs = json.loads(result["discogs_format_descs"])
    assert '12"' in descs
    assert "33 \u2153 RPM" in descs
    assert "Promo" in descs


# ---------------------------------------------------------------------------
# Field extraction — empty catno
# ---------------------------------------------------------------------------


def test_empty_catno_stored_as_none(config, mock_search_result, mock_release):
    label_mock = MagicMock()
    label_mock.id = 123
    label_mock.name = "Purpose Maker"
    label_mock.catno = ""  # empty string
    label_mock.entity_type_name = "Label"
    mock_release.labels = [label_mock]

    client = _make_client(search_results=[mock_search_result], release=mock_release)
    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    assert result["discogs_catno"] is None


# ---------------------------------------------------------------------------
# Failure — HTTPError 404 on release fetch
# ---------------------------------------------------------------------------


def test_http_404_on_release_fetch_returns_failure_dict(config, mock_search_result):
    import discogs_client.exceptions

    client = MagicMock()
    client.search.return_value = [mock_search_result]
    http_error = discogs_client.exceptions.HTTPError(404, "Not Found")
    client.release.side_effect = http_error

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    assert "discogs_error" in result
    assert result["discogs_release_id"] is None
    assert result["discogs_confidence"] == "none"


# ---------------------------------------------------------------------------
# Failure — TooManyAttemptsError
# ---------------------------------------------------------------------------


def test_too_many_attempts_error(config):
    import discogs_client.exceptions

    client = MagicMock()
    client.search.side_effect = discogs_client.exceptions.TooManyAttemptsError()

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    assert "discogs_error" in result
    assert "rate limit" in result["discogs_error"].lower()
    assert result["discogs_release_id"] is None


# ---------------------------------------------------------------------------
# Failure — unexpected exception
# ---------------------------------------------------------------------------


def test_unexpected_exception_does_not_propagate(config):
    # Candidate must score >= threshold so release() is called
    candidate = MagicMock()
    candidate.id = 1
    candidate.title = "Jeff Mills - The Bells"  # artist in title → +2
    candidate.catno = "PM-020"                  # catno exact match → +3
    candidate.year = "2006"                     # year exact match → +1
    candidate.format = ["Vinyl"]
    candidate.data_quality = "Correct"
    candidate.community = MagicMock(have=200, want=100)

    client = MagicMock()
    client.search.return_value = [candidate]
    client.release.side_effect = RuntimeError("unexpected internal error")

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    assert "discogs_error" in result
    assert result["discogs_release_id"] is None


# ---------------------------------------------------------------------------
# Master fetch enabled
# ---------------------------------------------------------------------------


def test_master_fetch_enabled(config, mock_search_result, mock_release):
    config_with_master = DiscogsConfig(
        discogs_token="test-token",
        user_agent="TestApp/1.0",
        fetch_master=True,
    )
    mock_release.master_id = 449968

    master_mock = MagicMock()
    master_mock.year = 1996
    master_mock.most_recent_release = 616407

    client = _make_client(
        search_results=[mock_search_result],
        release=mock_release,
        master=master_mock,
    )

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config_with_master,
    )

    assert result["discogs_master_year"] == 1996
    assert result["discogs_master_most_recent_id"] == 616407
    client.master.assert_called_once_with(449968)


# ---------------------------------------------------------------------------
# Master fetch disabled
# ---------------------------------------------------------------------------


def test_master_fetch_disabled(config, mock_search_result, mock_release):
    assert config.fetch_master is False

    client = _make_client(search_results=[mock_search_result], release=mock_release)

    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    client.master.assert_not_called()
    assert result["discogs_master_year"] is None
    assert result["discogs_master_most_recent_id"] is None


# ---------------------------------------------------------------------------
# Vinyl filter disabled
# ---------------------------------------------------------------------------


def test_vinyl_filter_disabled_skips_format_param(config, mock_search_result, mock_release):
    config_no_vinyl = DiscogsConfig(
        discogs_token="test-token",
        user_agent="TestApp/1.0",
        vinyl_filter_first=False,
    )
    search_calls = []

    def search_side_effect(**kwargs):
        search_calls.append(kwargs)
        return [mock_search_result]

    client = MagicMock()
    client.search.side_effect = search_side_effect
    client.release.return_value = mock_release

    fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno=None,
        barcode=None, year=2006, client=client, config=config_no_vinyl,
    )

    # No call should have format= kwarg
    assert all("format" not in c for c in search_calls)


# ---------------------------------------------------------------------------
# Happy path — label+title strategy
# ---------------------------------------------------------------------------


def test_label_title_strategy_fires_when_catno_and_barcode_fail(config, mock_search_result, mock_release):
    """label+title search is tried after catno and barcode both return nothing."""
    search_calls = []

    def search_side_effect(**kwargs):
        search_calls.append(kwargs)
        if "label" in kwargs and "track" in kwargs:
            return [mock_search_result]
        return []

    client = MagicMock()
    client.search.side_effect = search_side_effect
    client.release.return_value = mock_release

    result = fetch_discogs_metadata(
        artist="Jeff Mills",
        title="The Bells",
        label="Purpose Maker",
        catno=None,
        barcode=None,
        year=2006,
        client=client,
        config=config,
    )

    assert result["discogs_search_strategy"] == "label_title"
    assert result["discogs_release_id"] is not None
    assert any("label" in c for c in search_calls)


def test_label_title_skipped_when_catno_already_matched(config, mock_search_result, mock_release):
    """label+title is not attempted if catno already found results."""
    search_calls = []

    def search_side_effect(**kwargs):
        search_calls.append(kwargs)
        if "catno" in kwargs:
            return [mock_search_result]
        return []

    client = MagicMock()
    client.search.side_effect = search_side_effect
    client.release.return_value = mock_release

    result = fetch_discogs_metadata(
        artist="Jeff Mills",
        title="The Bells",
        label="Purpose Maker",
        catno="PM-020",
        barcode=None,
        year=2006,
        client=client,
        config=config,
    )

    assert result["discogs_search_strategy"] == "catno"
    assert all("label" not in c for c in search_calls)


def test_label_scoring_boosts_matching_candidate(config, mock_release):
    """A candidate whose label matches the input label gets a higher score."""
    # Candidate with label match — set .label as a list so _data_get returns it directly
    candidate_with_label = MagicMock()
    candidate_with_label.id = 616407
    candidate_with_label.title = "Some Release"
    candidate_with_label.catno = "XYZ-001"
    candidate_with_label.year = "2006"
    candidate_with_label.format = ["Vinyl"]
    candidate_with_label.data_quality = "Correct"
    candidate_with_label.community = MagicMock(have=50, want=20)
    candidate_with_label.label = ["Purpose Maker"]

    # Candidate without label match
    candidate_no_label = MagicMock()
    candidate_no_label.id = 999999
    candidate_no_label.title = "Some Release"
    candidate_no_label.catno = "XYZ-001"
    candidate_no_label.year = "2006"
    candidate_no_label.format = ["Vinyl"]
    candidate_no_label.data_quality = "Correct"
    candidate_no_label.community = MagicMock(have=50, want=20)
    candidate_no_label.label = ["Unknown Label"]

    client = _make_client(
        search_results=[candidate_no_label, candidate_with_label],
        release=mock_release,
    )

    result = fetch_discogs_metadata(
        artist=None,
        title="Some Release",
        label="Purpose Maker",
        catno=None,
        barcode=None,
        year=2006,
        client=client,
        config=config,
    )

    # The label-matching candidate (616407) should win
    client.release.assert_called_once_with(616407)


# ---------------------------------------------------------------------------
# Tracklist — heading/index entries excluded
# ---------------------------------------------------------------------------


def test_tracklist_excludes_non_track_entries(config, mock_search_result, mock_release):
    heading = MagicMock()
    heading.position = ""
    heading.title = "Side A"
    heading.duration = ""
    heading.type_ = "heading"

    track = MagicMock()
    track.position = "A1"
    track.title = "The Bells"
    track.duration = "9:05"
    track.type_ = "track"

    mock_release.tracklist = [heading, track]

    client = _make_client(search_results=[mock_search_result], release=mock_release)
    result = fetch_discogs_metadata(
        artist="Jeff Mills", title="The Bells", catno="PM-020",
        barcode=None, year=2006, client=client, config=config,
    )

    tracklist = json.loads(result["discogs_tracklist"])
    assert len(tracklist) == 1
    assert tracklist[0]["type_"] == "track"
    assert tracklist[0]["title"] == "The Bells"
