"""
Integration test for the interactive import flow against real audio files.

Submits a real `raw/` album through `POST /api/import`, drives the leader-elected `ImportWorker` (run as a
background task), answers the interactive decision it parks on, and verifies the album lands in the beets
library — queryable via `/api/query`.

Offline by design: beets 2.x exposes metadata sources (MusicBrainz, ...) as *plugins*, and beetkeeper does
not load beets plugins, so the importer finds no candidates and parks on a choose-match decision with an
empty candidate list — which we answer "as-is". No network, so this runs under the suite's `--disable-socket`.

Opt-in: tagged `requires_host_sources` by the directory conftest; run with `-m requires_host_sources` and
`BEETKEEPER_HOST_TEST_DIRPATH` set. The source album is copied to a temp dir and imported with `copy: yes`,
so the host files are never touched.
"""

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from ruamel.yaml import YAML


def _pick_single_album_dir(raw_dirpath: Path) -> Path:
    """Pick the single-album dir (audio files directly inside, no per-disc subdirs) with the fewest tracks."""
    candidates: list[tuple[int, Path]] = []
    for child in sorted(raw_dirpath.iterdir()):
        if child.is_dir():
            direct_audio = [f for f in child.iterdir() if f.suffix.lower() in {".flac", ".mp3", ".m4a"}]
            if direct_audio:
                candidates.append((len(direct_audio), child))
    if not candidates:
        pytest.skip("no single-album directory available under raw/ to import")
    return min(candidates)[1]


@pytest.fixture
async def import_env(tmp_path_factory: pytest.TempPathFactory, src_config_filepath: Path) -> AsyncIterator[tuple]:
    """Spin up a real import: empty beets library + migrated beetkeeper DB + a running `ImportWorker`.

    Yields `(client, source_album_path)`. The API routes are pointed at the same `ImportStore` the worker
    uses, and `get_beets_library` at the (initially empty) import library, so the import can be verified
    through `/api/query`.
    """
    from collections.abc import AsyncIterator as _AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from beetkeeper.api.dependencies import get_beets_library, get_import_store
    from beetkeeper.api.fastapi_app import beetkeeper_app
    from beetkeeper.core import BeetsLibrary, ImportStore, ImportWorker
    from beetkeeper.db import make_engine, make_sessionmaker, migrations
    from beetkeeper.db.session import get_session

    base = tmp_path_factory.mktemp("import_env")

    # Copy ONE album to import (copy:yes preserves it anyway, but copying keeps the host fully untouched).
    source_album = _pick_single_album_dir(src_config_filepath.parent / "raw")
    tmp_source = base / "source" / source_album.name
    shutil.copytree(source_album, tmp_source)

    # A copy of the beets config with an EMPTY library + a fresh import destination. Plugins are disabled
    # so the import stays offline + deterministic: no network-backed autotag plugin (musicbrainz/discogs/
    # bandcamp) loads, so beets finds no candidates and the import is answerable as-is (see CLAUDE.md's
    # no-network rule). beets' plugin registry is process-global, so the query-integration configs disable
    # plugins too (conftest) — otherwise a plugin loaded by an earlier test would leak into this one.
    config_data = YAML().load(src_config_filepath.read_text(encoding="utf-8"))
    config_data["library"] = str(base / "library.blb")
    config_data["directory"] = str(base / "dst")
    config_data["plugins"] = []
    beets_config_filepath = base / "config.yaml"
    with beets_config_filepath.open("w", encoding="utf-8") as config_file:
        YAML().dump(config_data, config_file)

    # A migrated beetkeeper DB for the import job store (alembic runs sync -> off the event loop).
    beetkeeper_db = base / "beetkeeper.db"
    alembic_cfg = migrations.make_alembic_config(
        async_url=f"sqlite+aiosqlite:///{beetkeeper_db}", sync_url=f"sqlite:///{beetkeeper_db}"
    )
    await anyio.to_thread.run_sync(migrations.upgrade, alembic_cfg, "head")

    engine = make_engine(f"sqlite+aiosqlite:///{beetkeeper_db}")
    sessionmaker = make_sessionmaker(engine)
    store = ImportStore(sessionmaker)
    worker = ImportWorker(beets_config_filepath, store)

    async def _override_get_session() -> "_AsyncIterator[AsyncSession]":
        async with sessionmaker() as session:
            yield session

    beetkeeper_app.dependency_overrides[get_import_store] = lambda: store
    beetkeeper_app.dependency_overrides[get_beets_library] = lambda: BeetsLibrary(beets_config_filepath)
    # The events fragment reads the same beetkeeper DB the worker records import events into.
    beetkeeper_app.dependency_overrides[get_session] = _override_get_session
    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(worker.run)
            transport = ASGITransport(app=beetkeeper_app)
            async with AsyncClient(transport=transport, base_url="http://testclient") as client:
                yield client, str(tmp_source)
            task_group.cancel_scope.cancel()
    finally:
        beetkeeper_app.dependency_overrides.clear()
        await engine.dispose()


async def _wait_for(client: AsyncClient, job_id: str, *, predicate, timeout: float = 60.0) -> dict:
    """Poll a job until `predicate(job)` is true (or timeout), returning the job."""
    with anyio.fail_after(timeout):
        while True:
            job = (await client.get(f"/api/import/{job_id}")).json()
            if predicate(job):
                return job
            await anyio.sleep(0.25)


@pytest.mark.anyio
async def test_import_album_with_interactive_decision_lands_in_library(import_env: tuple) -> None:
    client, album_path = import_env

    # The import library starts empty.
    assert (await client.get("/api/query/stats")).json()["tracks"] == 0

    # Submit the import; the background worker claims it and parks on a choose-match decision.
    job_id = (await client.post("/api/import", json={"paths": [album_path]})).json()["id"]
    job = await _wait_for(
        client,
        job_id,
        predicate=lambda j: j["status"] in {"awaiting_decision", "completed", "failed", "aborted"},
    )
    assert job["status"] == "awaiting_decision", f"expected a decision request; job={job}"
    assert job["pending_decision"] is not None

    # Answer it: apply the first candidate if beets found any, otherwise import as-is.
    candidates = job["pending_decision"]["candidates"]
    decision = {"action": "apply", "candidate_index": 0} if candidates else {"action": "asis"}
    assert (await client.post(f"/api/import/{job_id}/decision", json=decision)).status_code == 200

    # The worker resumes and completes the import.
    job = await _wait_for(client, job_id, predicate=lambda j: j["status"] in {"completed", "failed", "aborted"})
    assert job["status"] == "completed", f"import did not complete: {job}"

    # The job carries a human-readable output log of the run (rendered on the UI fragment).
    assert job["output"], "expected the completed job to have output"
    assert "Starting import of:" in job["output"]
    assert "Import completed." in job["output"]
    assert "Imported album:" in job["output"]

    # Verify it landed in the library, queryable via the API, with files under the destination directory.
    assert (await client.get("/api/query/stats")).json()["tracks"] > 0
    items = (await client.get("/api/query/list")).json()
    assert items
    assert all("/dst/" in (item.get("path") or "") for item in items)
    assert (await client.get("/api/query/list", params={"albums": "true"})).json()

    # The events page reflects the import: the worker recorded album/track listener events for it.
    events_fragment = (await client.get("/fragment/event")).text
    assert "album_imported" in events_fragment
    assert "item_imported" in events_fragment
