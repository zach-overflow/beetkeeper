"""
Integration tests for the read-only query API against a REAL beets library built from host audio files.

Opt-in only: run with `pytest -m requires_host_sources` and `BEETKEEPER_HOST_TEST_DIRPATH` set (see the
directory `conftest.py`). They exercise the full stack: HTTP route -> `BeetsLibrary` adapter -> a beets
`Library` populated from real audio tags.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_fields_lists_real_query_fields(integration_client: AsyncClient) -> None:
    body = (await integration_client.get("/api/query/fields")).json()
    assert "artist" in body["item_fields"]
    assert "album" in body["album_fields"]


@pytest.mark.anyio
async def test_stats_reports_nonzero_real_counts(integration_client: AsyncClient) -> None:
    body = (await integration_client.get("/api/query/stats")).json()
    assert body["tracks"] > 0
    assert body["albums"] > 0
    assert body["artists"] > 0
    assert body["total_time_seconds"] > 0


@pytest.mark.anyio
async def test_list_returns_real_items(integration_client: AsyncClient) -> None:
    items = (await integration_client.get("/api/query/list")).json()
    assert items, "the populated library should contain items"
    assert all("artist" in item and "title" in item for item in items)
    assert any(item["artist"] for item in items), "at least one item should have a non-empty artist tag"


@pytest.mark.anyio
async def test_list_albums_returns_real_albums(integration_client: AsyncClient) -> None:
    albums = (await integration_client.get("/api/query/list", params={"albums": "true"})).json()
    assert albums, "the populated library should contain albums"
    assert all("album" in album and "albumartist" in album for album in albums)


@pytest.mark.anyio
async def test_query_by_existing_artist_field(integration_client: AsyncClient) -> None:
    items = (await integration_client.get("/api/query/list")).json()
    some_artist = next(item["artist"] for item in items if item["artist"])

    matched = (await integration_client.get("/api/query/list", params={"field": f"artist:{some_artist}"})).json()
    assert matched, f"querying field=artist:{some_artist!r} should match the items it was taken from"
    assert any(item["artist"] == some_artist for item in matched)
    # An artist that cannot exist should match nothing.
    none = (
        await integration_client.get("/api/query/list", params={"field": "artist:__definitely_no_such_artist__"})
    ).json()
    assert none == []


@pytest.mark.anyio
async def test_stats_over_a_query_subset(integration_client: AsyncClient) -> None:
    items = (await integration_client.get("/api/query/list")).json()
    some_artist = next(item["artist"] for item in items if item["artist"])

    # /api/query/stats has no query params; the HTML search-stats fragment runs stats over a query.
    full = (await integration_client.get("/fragment/search/stats")).text
    subset = (await integration_client.get("/fragment/search/stats", params={"query": f"artist:{some_artist}"})).text
    assert "tracks" in full and "tracks" in subset
    assert "Query error" not in subset


@pytest.mark.anyio
async def test_search_results_fragment_renders_real_data(integration_client: AsyncClient) -> None:
    html = (await integration_client.get("/fragment/search/results", params={"query": ""})).text
    assert "found" in html  # "<n> tracks found."
    assert "<table" in html  # results rendered as a table
