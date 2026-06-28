"""Tests for the read-only `/api/query` routes against a real (empty) beets library.

`get_beets_library` is overridden with a `BeetsLibrary` pointed at a throwaway beets config, so these run
the actual beets query/stats/fields code paths (no music files, no network) and assert the JSON shape.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from beetkeeper.api.dependencies import get_beets_library
from beetkeeper.api.fastapi_app import beetkeeper_app
from beetkeeper.core import BeetsLibrary


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """A client whose `get_beets_library` dependency points at a fresh, empty beets library."""
    beets_config = tmp_path / "beets.yaml"
    beets_config.write_text(f"library: {tmp_path}/lib.db\ndirectory: {tmp_path}/music\n")
    library = BeetsLibrary(beets_config)
    beetkeeper_app.dependency_overrides[get_beets_library] = lambda: library
    try:
        transport = ASGITransport(app=beetkeeper_app)
        async with AsyncClient(transport=transport, base_url="http://testclient") as http_client:
            yield http_client
    finally:
        beetkeeper_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_list_empty_library_items_and_albums(client: AsyncClient) -> None:
    assert (await client.get("/api/query/list")).json() == []
    assert (await client.get("/api/query/list", params={"albums": "true"})).json() == []


@pytest.mark.anyio
async def test_list_accepts_repeatable_and_field_query_params(client: AsyncClient) -> None:
    # Empty library, but the keyword/field/sort params must parse into a valid beets query without error.
    response = await client.get(
        "/api/query/list", params={"keyword": ["foo", "bar"], "field": "artist:nobody", "sort_by": "year+"}
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_stats_shape_on_empty_library(client: AsyncClient) -> None:
    body = (await client.get("/api/query/stats")).json()
    assert body["tracks"] == 0
    assert body["albums"] == 0
    assert set(body) >= {
        "tracks",
        "total_time_minutes",
        "approximate_total_size_bytes",
        "artists",
        "albums",
        "album_artists",
    }


@pytest.mark.anyio
async def test_fields_lists_known_query_fields(client: AsyncClient) -> None:
    body = (await client.get("/api/query/fields")).json()
    assert "artist" in body["item_fields"]
    assert "albumartist" in body["album_fields"]
    assert isinstance(body["item_flexible_attributes"], list)
    assert isinstance(body["album_flexible_attributes"], list)
