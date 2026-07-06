"""Tests for the `/search` page and its HTMX fragments, against a real (empty) beets library.

`get_beets_library` is overridden with a `BeetsLibrary` pointed at a throwaway beets config (see this
package's `conftest.py`), so the fragments exercise the actual beets query/stats/fields paths and render
their templates.
"""

import pytest
from httpx import AsyncClient

from beetkeeper.api.dependencies import get_beets_library
from beetkeeper.core import BeetsLibrary

from .conftest import DependencyOverrides


@pytest.fixture
def app_dependency_overrides(beets_library: BeetsLibrary) -> DependencyOverrides:
    return {get_beets_library: lambda: beets_library}


@pytest.mark.anyio
async def test_search_page_renders(client: AsyncClient) -> None:
    response = await client.get("/search")
    assert response.status_code == 200
    body = response.text
    assert "Search the library" in body
    assert 'name="filepath"' in body
    assert ">List</button>" in body and ">Stats</button>" in body
    # Endpoints are wired via url_for, so a wrong endpoint name would 500 rather than just omit the string.
    assert "/fragment/search/results" in body
    assert "/fragment/search/stats" in body
    assert "/fragment/search/fields" in body


@pytest.mark.anyio
async def test_results_fragment_empty_library(client: AsyncClient) -> None:
    response = await client.get("/fragment/search/results", params={"query": ""})
    assert response.status_code == 200
    assert "No matches." in response.text


@pytest.mark.anyio
async def test_results_fragment_reports_query_error(client: AsyncClient) -> None:
    # `year` is numeric, so a non-numeric value is an invalid beets query: surfaced, not a 500.
    response = await client.get("/fragment/search/results", params={"query": "year:notanumber"})
    assert response.status_code == 200
    assert "Query error" in response.text


@pytest.mark.anyio
async def test_results_fragment_filepath_param(client: AsyncClient) -> None:
    empty = await client.get("/fragment/search/results", params={"query": "", "filepath": ""})
    assert empty.status_code == 200
    assert "No matches." in empty.text
    pathed = await client.get("/fragment/search/results", params={"filepath": "/music/nobody"})
    assert pathed.status_code == 200
    assert "No matches." in pathed.text


@pytest.mark.anyio
async def test_stats_fragment(client: AsyncClient) -> None:
    response = await client.get("/fragment/search/stats")
    assert response.status_code == 200
    assert "0" in response.text and "tracks" in response.text


@pytest.mark.anyio
async def test_stats_fragment_runs_over_the_query(client: AsyncClient) -> None:
    response = await client.get("/fragment/search/stats", params={"query": "artist:nobody", "filepath": ""})
    assert response.status_code == 200
    assert "tracks" in response.text
    assert "Query error" not in response.text


@pytest.mark.anyio
async def test_stats_fragment_reports_query_error(client: AsyncClient) -> None:
    response = await client.get("/fragment/search/stats", params={"query": "year:notanumber"})
    assert response.status_code == 200
    assert "Query error" in response.text


@pytest.mark.anyio
async def test_fields_fragment_lists_known_fields(client: AsyncClient) -> None:
    response = await client.get("/fragment/search/fields")
    assert response.status_code == 200
    assert "artist" in response.text
    assert "Item fields" in response.text
