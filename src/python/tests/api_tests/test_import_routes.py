"""Tests for the `/api/import` JSON routes, backed by a real `ImportStore` over a migrated temp DB.

`get_import_store` is overridden with a store bound to the test sessionmaker (no import worker runs; see
this package's `conftest.py`), so these cover submit/list/get/decision/abort against actual persisted rows.
"""

from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.api.dependencies import get_beets_library, get_downloader_hook, get_import_store
from beetkeeper.core import BeetsLibrary, ImportStore
from beetkeeper.db.models import InferredSourcePath
from beetkeeper.db.session import get_session
from beetkeeper.hooks import DownloaderHook
from beetkeeper.settings import DownloaderHookConfSection

from .conftest import DependencyOverrides, SessionOverride


@pytest.fixture
def app_dependency_overrides(import_store: ImportStore) -> DependencyOverrides:
    return {get_import_store: lambda: import_store}


@pytest.mark.anyio
async def test_submit_creates_pending_job_and_is_fetchable(client: AsyncClient) -> None:
    response = await client.post("/api/import", json={"paths": ["/music/incoming/album"]})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["paths"] == ["/music/incoming/album"]

    fetched = await client.get(f"/api/import/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


@pytest.mark.anyio
async def test_submit_defaults_to_interactive(client: AsyncClient) -> None:
    body = (await client.post("/api/import", json={"paths": ["/m/1"]})).json()
    assert body["quiet"] is False


@pytest.mark.anyio
async def test_submit_quiet_flag_is_recorded(client: AsyncClient) -> None:
    body = (await client.post("/api/import", json={"paths": ["/m/1"], "quiet": True})).json()
    assert body["status"] == "pending"
    assert body["quiet"] is True
    assert (await client.get(f"/api/import/{body['id']}")).json()["quiet"] is True


@pytest.mark.anyio
async def test_submit_records_per_job_import_settings(client: AsyncClient) -> None:
    payload = {
        "paths": ["/m/1"],
        "quiet": True,
        "logpath": "/logs/import.log",
        "group_albums": True,
        "flat": True,
        "set_fields": {"genre": "Jazz"},
    }
    body = (await client.post("/api/import", json=payload)).json()
    assert body["status"] == "pending"
    assert body["logpath"] == "/logs/import.log"
    assert body["group_albums"] is True
    assert body["flat"] is True
    assert body["set_fields"] == {"genre": "Jazz"}

    fetched = (await client.get(f"/api/import/{body['id']}")).json()
    assert fetched["logpath"] == "/logs/import.log"
    assert fetched["group_albums"] is True
    assert fetched["flat"] is True
    assert fetched["set_fields"] == {"genre": "Jazz"}


@pytest.mark.anyio
async def test_submit_settings_default_to_beets_config(client: AsyncClient) -> None:
    """Unspecified settings resolve from beets' config (the test env has beets' shipped defaults)."""
    body = (await client.post("/api/import", json={"paths": ["/m/1"]})).json()
    assert body["logpath"] is None
    assert body["group_albums"] is False
    assert body["flat"] is False
    assert body["set_fields"] == {}


@pytest.mark.anyio
async def test_list_imports_returns_submitted_jobs(client: AsyncClient) -> None:
    await client.post("/api/import", json={"paths": ["/m/1"]})
    await client.post("/api/import", json={"paths": ["/m/2"]})
    response = await client.get("/api/import")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.anyio
async def test_list_imports_is_paginated_newest_first(client: AsyncClient) -> None:
    job_ids = [(await client.post("/api/import", json={"paths": [f"/m/{n}"]})).json()["id"] for n in range(3)]
    newest_first = list(reversed(job_ids))

    first_page = (await client.get("/api/import", params={"page_size": 2})).json()
    assert [job["id"] for job in first_page] == newest_first[:2]

    second_page = (await client.get("/api/import", params={"page": 2, "page_size": 2})).json()
    assert [job["id"] for job in second_page] == newest_first[2:]

    assert (await client.get("/api/import", params={"page_size": 101})).status_code == 422


@pytest.mark.anyio
async def test_decision_on_non_awaiting_job_conflicts(client: AsyncClient) -> None:
    job_id = (await client.post("/api/import", json={"paths": ["/m/1"]})).json()["id"]
    response = await client.post(f"/api/import/{job_id}/decision", json={"action": "skip"})
    assert response.status_code == 409


@pytest.mark.anyio
async def test_empty_paths_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/import", json={"paths": []})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_unknown_job_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/import/nope")).status_code == 404
    assert (await client.post("/api/import/nope/decision", json={"action": "skip"})).status_code == 404
    assert (await client.post("/api/import/nope/abort")).status_code == 404


@pytest.mark.anyio
async def test_health_reports_pid_and_shared_job_count(client: AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    assert isinstance(body["process_pid"], int)
    assert body["import_lock_holder"] is None
    assert body["is_import_leader"] is False
    before = body["job_count"]

    await client.post("/api/import", json={"paths": ["/m/x"]})
    assert (await client.get("/api/health")).json()["job_count"] == before + 1


@pytest.mark.anyio
async def test_reimport_creates_pending_library_job(client: AsyncClient) -> None:
    payload = {
        "query": ["albumartist:Bonobo", "year:2010"],
        "singletons": False,
        "quiet": True,
        "move_files": False,
        "write_tags": False,
        "set_fields": {"mood": "calm"},
    }
    response = await client.post("/api/import/reimport", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["is_reimport"] is True
    assert body["paths"] == []
    assert body["query"] == ["albumartist:Bonobo", "year:2010"]
    assert (body["quiet"], body["move_files"], body["write_tags"]) == (True, False, False)
    assert body["set_fields"] == {"mood": "calm"}
    assert body["reimport_report"] is None

    assert (await client.get(f"/api/import/{body['id']}")).json()["query"] == payload["query"]


@pytest.mark.anyio
async def test_reimport_file_handling_defaults_follow_beets_config(client: AsyncClient) -> None:
    body = (await client.post("/api/import/reimport", json={"query": ["album:A"]})).json()
    # beets ships `copy: yes` / `write: yes`, and `copy` relocates files that are already in the library.
    assert (body["move_files"], body["write_tags"], body["singletons"]) == (True, True, False)


@pytest.mark.anyio
async def test_reimport_accepts_explicit_empty_query_for_the_entire_library(client: AsyncClient) -> None:
    body = (await client.post("/api/import/reimport", json={"query": []})).json()
    assert body["query"] == []
    assert body["source_label"] == "reimport: entire library"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="query-is-required"),
        pytest.param({"query": ["a"], "paths": ["/m/1"]}, id="paths-are-not-accepted"),
        pytest.param({"query": "album:A"}, id="query-must-be-a-list"),
    ],
)
async def test_reimport_rejects_invalid_bodies(client: AsyncClient, payload: dict[str, object]) -> None:
    assert (await client.post("/api/import/reimport", json=payload)).status_code == 422


@pytest.mark.anyio
async def test_path_import_is_not_flagged_as_reimport(client: AsyncClient) -> None:
    body = (await client.post("/api/import", json={"paths": ["/m/1"]})).json()
    assert body["is_reimport"] is False
    assert body["query"] is None


class TestFindMissingSourcePathWithoutHook:
    @pytest.fixture
    def app_dependency_overrides(
        self, import_store: ImportStore, beets_library: BeetsLibrary, get_session_override: SessionOverride
    ) -> DependencyOverrides:
        return {
            get_import_store: lambda: import_store,
            get_beets_library: lambda: beets_library,
            get_session: get_session_override,
        }

    @pytest.mark.anyio
    async def test_conflicts_without_a_downloader_hook(self, client: AsyncClient) -> None:
        response = await client.get("/api/import/reimport/find_missing_source_path", params={"beets_album_id": 1})
        assert response.status_code == 409
        assert "downloader_hook" in response.json()["detail"]


class TestFindMissingSourcePath:
    """The lookup route against a populated beets library and a mock-transport downloader API."""

    @pytest.fixture
    def downloader_requests(self) -> list[httpx.Request]:
        return []

    @pytest.fixture
    def downloader_hook(self, downloader_requests: list[httpx.Request]) -> DownloaderHook:
        def handler(request: httpx.Request) -> httpx.Response:
            downloader_requests.append(request)
            if request.url.params.get("artist") == "Artist 07":
                return httpx.Response(200, json=[{"content_path": "/data/complete/Artist 07 - Album"}])
            return httpx.Response(200, json=[])

        config = DownloaderHookConfSection(
            base_url="http://qbit.local:8080",
            search_endpoint_path="/api/v2/torrents/info",
            beets_field_names_to_query_param_names={"album": "name", "albumartist": "artist"},
            filepath_json_key="content_path",
            replace_downloader_paths_prefix="/data/complete",
        )
        return DownloaderHook(config, Path("/downloads"), transport=httpx.MockTransport(handler))

    @pytest.fixture
    def app_dependency_overrides(
        self,
        import_store: ImportStore,
        populated_beets_library: BeetsLibrary,
        downloader_hook: DownloaderHook,
        get_session_override: SessionOverride,
    ) -> DependencyOverrides:
        return {
            get_import_store: lambda: import_store,
            get_beets_library: lambda: populated_beets_library,
            get_downloader_hook: lambda: downloader_hook,
            get_session: get_session_override,
        }

    @pytest.mark.anyio
    async def test_track_lookup_searches_with_renamed_fields(
        self, client: AsyncClient, downloader_requests: list[httpx.Request]
    ) -> None:
        response = await client.get("/api/import/reimport/find_missing_source_path", params={"beets_item_id": 8})
        assert response.status_code == 200
        body = response.json()
        assert body["found_match"] is True
        assert body["source_directory"] == "/downloads/Artist 07 - Album"
        assert body["search_status_code"] == 200
        assert body["query_params"] == {"name": "Album", "artist": "Artist 07"}
        assert body["recorded_inference"] is True

        (request,) = downloader_requests
        assert request.url.path == "/api/v2/torrents/info"
        assert dict(request.url.params) == {"name": "Album", "artist": "Artist 07"}

    @pytest.mark.anyio
    async def test_album_lookup_reports_no_match(
        self, client: AsyncClient, populated_beets_library: BeetsLibrary
    ) -> None:
        # The synthetic library holds items only; add one album so an album id resolves.
        from beets.library import Item, Library

        library = Library(str(populated_beets_library._beets_config_filepath.parent / "lib.db"))
        album = library.add_album([Item(album="Other", albumartist="Someone", path=b"/music/o.mp3")])

        body = (
            await client.get("/api/import/reimport/find_missing_source_path", params={"beets_album_id": album.id})
        ).json()
        assert body["found_match"] is False
        assert body["source_directory"] is None
        assert body["detail"] == "No search results."

    @pytest.mark.anyio
    async def test_match_is_stored_as_an_inference_and_replaced_on_relookup(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        for _ in range(2):
            await client.get("/api/import/reimport/find_missing_source_path", params={"beets_item_id": 8})

        async with session_factory() as session:
            rows = (await session.execute(select(InferredSourcePath))).scalars().all()
        (row,) = rows
        assert (row.subject_type, row.beets_id, row.method) == ("track", 8, "downloader_hook")
        assert row.source_path == "/downloads/Artist 07 - Album"
        assert row.query_params_json == '{"name": "Album", "artist": "Artist 07"}'

    @pytest.mark.anyio
    async def test_no_match_stores_nothing(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        body = (await client.get("/api/import/reimport/find_missing_source_path", params={"beets_item_id": 3})).json()
        assert body["found_match"] is False and body["recorded_inference"] is False
        async with session_factory() as session:
            assert (await session.execute(select(InferredSourcePath))).scalars().all() == []

    @pytest.mark.anyio
    async def test_unknown_id_is_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/import/reimport/find_missing_source_path", params={"beets_item_id": 999})
        assert response.status_code == 404

    @pytest.mark.anyio
    @pytest.mark.parametrize("params", [{}, {"beets_album_id": 1, "beets_item_id": 2}, {"beets_item_id": "x"}])
    async def test_exactly_one_id_is_required(self, client: AsyncClient, params: dict[str, str | int]) -> None:
        assert (await client.get("/api/import/reimport/find_missing_source_path", params=params)).status_code == 422
