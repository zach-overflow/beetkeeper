"""Tests for the `/search` page and its HTMX fragments, against a real (empty) beets library.

`get_beets_library` is overridden with a `BeetsLibrary` pointed at a throwaway beets config (see this
package's `conftest.py`), so the fragments exercise the actual beets query/stats/fields paths and render
their templates.
"""

from pathlib import Path

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
async def test_page_urls_are_root_relative(client: AsyncClient) -> None:
    """Generated asset/HTMX URLs must be root-relative: absolute ones bake in the scheme/host the server
    guessed, which browsers block as mixed content behind a TLS-terminating proxy it doesn't know about."""
    body = (await client.get("/search")).text
    assert 'src="/static/js/htmx.min.js"' in body
    assert 'hx-get="/fragment/search/results"' in body
    assert "http://testserver" not in body  # the AsyncClient base_url; absolute url_for would leak it


@pytest.mark.anyio
async def test_search_page_does_not_autoload_stats(client: AsyncClient) -> None:
    """The unbounded stats query must only run when the user clicks the Stats button, never on page open."""
    body = (await client.get("/search")).text
    assert "library-stats" not in body
    stats_elements = [line for line in body.splitlines() if "/fragment/search/stats" in line]
    assert stats_elements, "the Stats button should still reference the stats fragment"
    assert all("hx-trigger" not in line for line in stats_elements)


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


class TestResultsFragmentPagination:
    """The results fragment must render bounded pages, never the full (potentially huge) match list."""

    @pytest.fixture
    def app_dependency_overrides(self, populated_beets_library: BeetsLibrary) -> DependencyOverrides:
        return {get_beets_library: lambda: populated_beets_library}

    @pytest.mark.anyio
    async def test_first_page_is_default_size_with_next_control(self, client: AsyncClient) -> None:
        response = await client.get("/fragment/search/results")
        assert response.status_code == 200
        body = response.text
        assert "Showing 1–25 of 30 tracks." in body
        assert "Song 00" in body and "Song 24" in body and "Song 25" not in body
        assert ">Next</button>" in body
        assert ">Previous</button>" not in body

    @pytest.mark.anyio
    async def test_second_page_holds_the_remainder(self, client: AsyncClient) -> None:
        response = await client.get("/fragment/search/results", params={"page": 2})
        assert response.status_code == 200
        body = response.text
        assert "Showing 26–30 of 30 tracks." in body
        assert "Song 25" in body and "Song 29" in body and "Song 24" not in body
        assert ">Previous</button>" in body
        assert ">Next</button>" not in body

    @pytest.mark.anyio
    async def test_page_size_is_capped(self, client: AsyncClient) -> None:
        assert (await client.get("/fragment/search/results", params={"page_size": 101})).status_code == 422
        response = await client.get("/fragment/search/results", params={"page_size": 5, "page": 2})
        assert "Showing 6–10 of 30 tracks." in response.text

    @pytest.mark.anyio
    async def test_past_the_end_page_offers_a_way_back(self, client: AsyncClient) -> None:
        response = await client.get("/fragment/search/results", params={"page": 5})
        assert response.status_code == 200
        body = response.text
        assert "No results on this page — 30 tracks match." in body
        assert ">Back to first page</button>" in body
        assert "No matches." not in body

    @pytest.mark.anyio
    async def test_paging_controls_carry_the_query_params(self, client: AsyncClient) -> None:
        response = await client.get("/fragment/search/results", params={"query": "artist:Artist", "page_size": 5})
        body = response.text
        assert "query=artist%3AArtist" in body
        assert "page_size=5" in body
        assert "page=2" in body


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
