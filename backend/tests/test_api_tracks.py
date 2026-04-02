"""
Tests for GET /tracks — the track library endpoint.
"""

from fastapi.testclient import TestClient


def test_get_tracks_returns_200(client: TestClient) -> None:
    """
    GET /tracks must return HTTP 200.

    The most basic smoke test: is the endpoint reachable at all?
    A 404 means the router is not registered; a 500 means something
    crashed at startup.
    """
    response = client.get("/tracks")
    assert (
        response.status_code == 200
    ), f"Expected 200 but got {response.status_code}: {response.text}"


def test_get_tracks_returns_empty_list_when_no_tracks(client: TestClient) -> None:
    """
    GET /tracks must return an empty list when no tracks have been imported.

    Why test this specifically?
    An empty list [] is different from null, an empty object {}, or
    a 404. The frontend depends on the response being a list it can
    iterate over. If this changes, the frontend breaks silently.
    """
    response = client.get("/tracks")
    data = response.json()
    assert isinstance(data, list), f"Expected a list, got: {type(data)}"
    assert len(data) == 0, f"Expected empty list, got {len(data)} items"
