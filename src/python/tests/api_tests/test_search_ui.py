"""Tests for the `/search` page and its HTMX fragments, against a real (empty) beets library.

`get_beets_library` is overridden with a `BeetsLibrary` pointed at a throwaway beets config (see this
package's `conftest.py`), so the fragments exercise the actual beets query/stats/fields paths and render
their templates. `get_session` is overridden onto a freshly-migrated temp beetkeeper DB, which the results
fragment reads for the import source paths recorded by the plugin's `/api/events/filesystem` pushes.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

from beetkeeper.api.dependencies import get_beets_library
from beetkeeper.core import BeetsLibrary
from beetkeeper.db.session import get_session

from .conftest import DependencyOverrides, SessionOverride


@pytest.fixture
def app_dependency_overrides(beets_library: BeetsLibrary, get_session_override: SessionOverride) -> DependencyOverrides:
    return {get_beets_library: lambda: beets_library, get_session: get_session_override}


@pytest.fixture
def album_beets_library(tmp_path: Path) -> BeetsLibrary:
    """A `BeetsLibrary` over a throwaway beets config holding one two-track album (album id 1, items 1-2)."""
    from beets.library import Item, Library

    beets_config = tmp_path / "beets.yaml"
    beets_config.write_text(f"library: {tmp_path}/lib.db\ndirectory: {tmp_path}/music\n")
    library = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    library.add_album(
        [
            Item(
                artist="Artist",
                albumartist="Artist",
                album="An Album",
                title=f"Song {index}",
                track=index,
                year=2000,
                path=f"/music/An Album/{index:02d} song.mp3".encode(),
            )
            for index in (1, 2)
        ]
    )
    return BeetsLibrary(beets_config)


def _filesystem_event_payload(
    pushed_at: str, source_paths: list[str], track_ids: list[int], album_id: int | None
) -> dict[str, object]:
    """An `import_task_files` push recording `source_paths` for the given beets item ids (and album id)."""
    return {
        "event_type": "import_task_files",
        "pushed_at": pushed_at,
        "choice_flag": "APPLY",
        "source_paths": source_paths,
        "imported_items": [
            {
                "event_type": "import_task_files",
                "pushed_at": pushed_at,
                "track_fields": {"id": track_id, "album_id": album_id, "path": f"/music/{track_id}.mp3"},
            }
            for track_id in track_ids
        ],
    }


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
    def app_dependency_overrides(
        self, populated_beets_library: BeetsLibrary, get_session_override: SessionOverride
    ) -> DependencyOverrides:
        return {get_beets_library: lambda: populated_beets_library, get_session: get_session_override}

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


class TestResultsFragmentPaths:
    """Every track row shows its library path and either its recorded import source path(s) or an explicit
    "not recorded" marker (imports the beetkeeper plugin never reported), plus a page-level notice."""

    @pytest.fixture
    def app_dependency_overrides(
        self, populated_beets_library: BeetsLibrary, get_session_override: SessionOverride
    ) -> DependencyOverrides:
        return {get_beets_library: lambda: populated_beets_library, get_session: get_session_override}

    @pytest.mark.anyio
    async def test_rows_without_recorded_import_are_flagged(self, client: AsyncClient) -> None:
        response = await client.get("/fragment/search/results", params={"page_size": 5, "sort_by": "title+"})
        assert response.status_code == 200
        body = response.text
        assert "<th>Source path(s)</th>" in body and "<th>Destination path</th>" in body
        assert "<code>/music/song00.mp3</code>" in body
        assert body.count(">Not recorded</em>") == 5
        assert "5 of the tracks on this page have no recorded source path." in body
        assert "beetkeeper beets plugin" in body

    @pytest.mark.anyio
    async def test_recorded_source_paths_render_per_track(self, client: AsyncClient, pushed_at: str) -> None:
        # Items are added in title order, so "Song 00" and "Song 01" hold beets item ids 1 and 2.
        payload = _filesystem_event_payload(pushed_at, ["/inbox/song00.flac", "/inbox/song00.cue"], [1], None)
        assert (await client.post("/api/events/filesystem", json=payload)).status_code == 201
        payload = _filesystem_event_payload(pushed_at, ["/inbox/song01.flac"], [2], None)
        assert (await client.post("/api/events/filesystem", json=payload)).status_code == 201

        response = await client.get("/fragment/search/results", params={"page_size": 5, "sort_by": "title+"})
        assert response.status_code == 200
        body = response.text
        assert "<summary>2 paths</summary>" in body
        assert "<code>/inbox/song00.flac</code>" in body and "<code>/inbox/song00.cue</code>" in body
        assert "<code>/inbox/song01.flac</code>" in body
        assert body.count(">Not recorded</em>") == 3
        assert "3 of the tracks on this page have no recorded source path." in body

    @pytest.mark.anyio
    async def test_notice_is_omitted_when_every_row_has_a_source(self, client: AsyncClient, pushed_at: str) -> None:
        payload = _filesystem_event_payload(pushed_at, ["/inbox/batch"], [1, 2], None)
        assert (await client.post("/api/events/filesystem", json=payload)).status_code == 201

        response = await client.get("/fragment/search/results", params={"page_size": 2, "sort_by": "title+"})
        body = response.text
        assert body.count("<code>/inbox/batch</code>") == 2
        assert "Not recorded" not in body
        assert "missing-source-notice" not in body


class TestAlbumResultsFragmentPaths:
    """Album rows show the album directory as their destination and the import's recorded source paths."""

    @pytest.fixture
    def app_dependency_overrides(
        self, album_beets_library: BeetsLibrary, get_session_override: SessionOverride
    ) -> DependencyOverrides:
        return {get_beets_library: lambda: album_beets_library, get_session: get_session_override}

    @pytest.mark.anyio
    async def test_album_without_recorded_import_is_flagged(self, client: AsyncClient) -> None:
        response = await client.get("/fragment/search/results", params={"albums": "true"})
        assert response.status_code == 200
        body = response.text
        assert "Showing 1–1 of 1 albums." in body
        assert "<code>/music/An Album</code>" in body
        assert body.count(">Not recorded</em>") == 1
        assert "1 of the albums on this page has no recorded source path." in body

    @pytest.mark.anyio
    async def test_album_source_paths_come_from_its_tracks_import(self, client: AsyncClient, pushed_at: str) -> None:
        payload = _filesystem_event_payload(pushed_at, ["/inbox/An Album"], [1, 2], 1)
        assert (await client.post("/api/events/filesystem", json=payload)).status_code == 201

        response = await client.get("/fragment/search/results", params={"albums": "true"})
        body = response.text
        assert body.count("<code>/inbox/An Album</code>") == 1
        assert "<code>/music/An Album</code>" in body
        assert "Not recorded" not in body
        assert "missing-source-notice" not in body


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
