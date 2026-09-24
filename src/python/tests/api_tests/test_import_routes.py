"""Tests for the `/api/import` JSON routes, backed by a real `ImportStore` over a migrated temp DB.

`get_import_store` is overridden with a store bound to the test sessionmaker (no import worker runs; see
this package's `conftest.py`), so these cover submit/list/get/decision/abort against actual persisted rows.
The clean-slate routes run against a throwaway beets library holding real (tiny) WAV files.
"""

from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.api.dependencies import get_beets_library, get_downloader_hook, get_import_store, get_user_config
from beetkeeper.core import BeetsLibrary, ImportStore
from beetkeeper.db.models import InferredSourcePath
from beetkeeper.db.session import get_session
from beetkeeper.hooks import DownloaderHook
from beetkeeper.settings import DownloaderHookConfSection, UserConfig
from tests.conftest import TaggedWavWriter

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
async def test_path_import_is_not_a_clean_slate(client: AsyncClient) -> None:
    body = (await client.post("/api/import", json={"paths": ["/m/1"]})).json()
    assert body["is_clean_slate"] is False
    assert (body["clean_slate_album_id"], body["clean_slate_item_id"]) == (None, None)
    assert body["source_label"] == "1"


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


@pytest.fixture
def wav_album_library(tmp_path: Path, make_tagged_wav: TaggedWavWriter) -> BeetsLibrary:
    """A library (config shared with `user_config`) holding one two-track album whose second file is gone."""
    from beets.library import Item, Library

    beets_config = tmp_path / "beets.yaml"
    beets_config.write_text(f"library: {tmp_path}/lib.db\ndirectory: {tmp_path}/music\n", encoding="utf-8")
    library = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    items = []
    for track, title in ((1, "One"), (2, "Two")):
        path = tmp_path / "music" / "Artist" / "Album" / f"{track:02d} {title}.wav"
        make_tagged_wav(
            path, title=title, artist="Artist", albumartist="Artist", album="Album", track=track, tracktotal=2
        )
        items.append(Item.from_path(path))
    library.add_album(items)
    (tmp_path / "music" / "Artist" / "Album" / "02 Two.wav").unlink()
    return BeetsLibrary(beets_config)


@pytest.fixture
def source_folder(downloads_path: Path, make_tagged_wav: TaggedWavWriter) -> Path:
    """The album's raw download folder under `downloads_path`, holding both tracks."""
    folder = downloads_path / "Artist - Album"
    for track, title in ((1, "One"), (2, "Two")):
        make_tagged_wav(
            folder / f"{track:02d} {title}.wav",
            title=title,
            artist="Artist",
            albumartist="Artist",
            album="Album",
            track=track,
            tracktotal=2,
        )
    return folder


class TestCleanSlate:
    @pytest.fixture
    def app_dependency_overrides(
        self, import_store: ImportStore, wav_album_library: BeetsLibrary, user_config: UserConfig
    ) -> DependencyOverrides:
        return {
            get_import_store: lambda: import_store,
            get_beets_library: lambda: wav_album_library,
            get_user_config: lambda: user_config,
        }

    @pytest.mark.anyio
    async def test_preview_reports_the_plan_without_touching_anything(
        self, client: AsyncClient, source_folder: Path, tmp_path: Path
    ) -> None:
        response = await client.get(
            "/api/import/clean_slate/preview", params={"beets_album_id": 1, "source_path": str(source_folder)}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True and body["errors"] == [] and body["warnings"] == []
        assert (body["subject"], body["beets_id"], body["label"]) == ("album", 1, "Artist - Album")
        assert (body["item_count"], body["files_present"], body["files_missing"], body["expected_tracks"]) == (
            2,
            1,
            1,
            2,
        )
        assert body["files_to_delete"] == [str(tmp_path / "music" / "Artist" / "Album" / "01 One.wav")]
        assert body["missing_paths"] == [str(tmp_path / "music" / "Artist" / "Album" / "02 Two.wav")]
        assert (body["source_audio_files"], body["source_album_groups"]) == (2, 1)
        assert (tmp_path / "music" / "Artist" / "Album" / "01 One.wav").exists()

    @pytest.mark.anyio
    async def test_submit_creates_a_clean_slate_job(self, client: AsyncClient, source_folder: Path) -> None:
        payload = {"beets_album_id": 1, "source_path": str(source_folder), "quiet": True, "set_fields": {"mood": "x"}}
        response = await client.post("/api/import/clean_slate", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending" and body["is_clean_slate"] is True
        assert (body["clean_slate_album_id"], body["clean_slate_item_id"]) == (1, None)
        assert body["clean_slate_allow_fewer_files"] is False
        assert body["paths"] == [str(source_folder)]
        assert body["source_label"] == "clean slate: Artist - Album"
        assert body["quiet"] is True and body["set_fields"] == {"mood": "x"}
        assert (await client.get(f"/api/import/{body['id']}")).json()["clean_slate_album_id"] == 1

    @pytest.mark.anyio
    async def test_submit_refuses_a_blocking_error(
        self, client: AsyncClient, tmp_path: Path, make_tagged_wav: TaggedWavWriter, import_store: ImportStore
    ) -> None:
        outside = make_tagged_wav(tmp_path / "elsewhere" / "Album" / "01 One.wav", title="One", artist="Artist")
        response = await client.post(
            "/api/import/clean_slate", json={"beets_album_id": 1, "source_path": str(outside.parent)}
        )
        assert response.status_code == 422
        assert "must be a folder inside" in response.json()["detail"]
        assert await import_store.list() == []

    @pytest.mark.anyio
    async def test_submit_needs_the_opt_in_when_the_source_has_fewer_files(
        self, client: AsyncClient, downloads_path: Path, make_tagged_wav: TaggedWavWriter, tmp_path: Path
    ) -> None:
        # The library has one file on disk; give it a second one so a one-file source is "fewer".
        make_tagged_wav(tmp_path / "music" / "Artist" / "Album" / "02 Two.wav", title="Two", artist="Artist")
        short = make_tagged_wav(downloads_path / "Artist - Album" / "01 One.wav", title="One", artist="Artist").parent
        payload = {"beets_album_id": 1, "source_path": str(short)}

        refused = await client.post("/api/import/clean_slate", json=payload)
        assert refused.status_code == 409
        assert "allow_fewer_files" in refused.json()["detail"]

        accepted = await client.post("/api/import/clean_slate", json=payload | {"allow_fewer_files": True})
        assert accepted.status_code == 201
        assert accepted.json()["clean_slate_allow_fewer_files"] is True

    @pytest.mark.anyio
    async def test_unknown_entry_is_404(self, client: AsyncClient, source_folder: Path) -> None:
        params: dict[str, str | int] = {"beets_item_id": 999, "source_path": str(source_folder)}
        assert (await client.get("/api/import/clean_slate/preview", params=params)).status_code == 404
        assert (await client.post("/api/import/clean_slate", json=params)).status_code == 404

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"source_path": "/x"}, id="no-id"),
            pytest.param({"beets_album_id": 1, "beets_item_id": 2, "source_path": "/x"}, id="both-ids"),
            pytest.param({"beets_album_id": 1}, id="no-source"),
            pytest.param({"beets_album_id": 1, "source_path": "/x", "paths": ["/y"]}, id="unknown-field"),
        ],
    )
    async def test_invalid_bodies_are_422(self, client: AsyncClient, payload: dict[str, object]) -> None:
        assert (await client.post("/api/import/clean_slate", json=payload)).status_code == 422


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
        response = await client.post("/api/import/find_missing_source_path", json={"beets_album_id": 1})
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
        response = await client.post("/api/import/find_missing_source_path", json={"beets_item_id": 8})
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

        body = (await client.post("/api/import/find_missing_source_path", json={"beets_album_id": album.id})).json()
        assert body["found_match"] is False
        assert body["source_directory"] is None
        assert body["detail"] == "No search results."

    @pytest.mark.anyio
    async def test_match_is_stored_as_an_inference_and_replaced_on_relookup(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        for _ in range(2):
            await client.post("/api/import/find_missing_source_path", json={"beets_item_id": 8})

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
        body = (await client.post("/api/import/find_missing_source_path", json={"beets_item_id": 3})).json()
        assert body["found_match"] is False and body["recorded_inference"] is False
        async with session_factory() as session:
            assert (await session.execute(select(InferredSourcePath))).scalars().all() == []

    @pytest.mark.anyio
    async def test_unknown_id_is_404(self, client: AsyncClient) -> None:
        response = await client.post("/api/import/find_missing_source_path", json={"beets_item_id": 999})
        assert response.status_code == 404

    @pytest.mark.anyio
    @pytest.mark.parametrize("body", [{}, {"beets_album_id": 1, "beets_item_id": 2}, {"beets_item_id": "x"}])
    async def test_exactly_one_id_is_required(self, client: AsyncClient, body: dict[str, str | int]) -> None:
        assert (await client.post("/api/import/find_missing_source_path", json=body)).status_code == 422
