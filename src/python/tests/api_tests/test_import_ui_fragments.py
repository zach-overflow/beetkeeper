"""Renders the import job HTMX fragment for a job awaiting a decision, asserting the candidate table HTML.

Backed by a real `ImportStore` over a migrated temp DB (no import worker runs); this exercises the full
`import_job.html` template, so it also guards against Jinja errors in the candidate-table markup.
"""

import importlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.api.dependencies import get_import_store
from beetkeeper.api.fastapi_app import beetkeeper_app
from beetkeeper.core import ImportJobStatus, ImportStore
from beetkeeper.core.import_jobs import DecisionRequest, ImportAction, ImportCandidate

# The import-fragments *submodule* (resolved via importlib, since the `ui_routes` package re-exports the
# router under the same name, shadowing the submodule for attribute access). Suggestion tests monkeypatch
# its `_IMPORT_ROOT` to a temp directory.
_import_fragments_mod = importlib.import_module("beetkeeper.api.ui_routes.import_ui_fragments_router")


@pytest.fixture
async def client_and_store(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[AsyncClient, ImportStore]]:
    store = ImportStore(session_factory)
    beetkeeper_app.dependency_overrides[get_import_store] = lambda: store
    try:
        transport = ASGITransport(app=beetkeeper_app)
        async with AsyncClient(transport=transport, base_url="http://testclient") as http_client:
            yield http_client, store
    finally:
        beetkeeper_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_decision_fragment_renders_candidate_table(client_and_store: tuple[AsyncClient, ImportStore]) -> None:
    http_client, store = client_and_store
    job = await store.create(["/m/a"])
    await store.set_awaiting(
        DecisionRequest(
            job_id=job.id,
            task_id="t",
            prompt="Choose a match for this album.",
            candidates=[
                ImportCandidate(
                    index=0,
                    label="A - B",
                    similarity=0.99,
                    year=2026,
                    media="Digital Media",
                    data_source="MusicBrainz",
                    album_id="id0",
                ),
                ImportCandidate(
                    index=1,
                    label="A - B",
                    similarity=0.90,
                    year=2007,
                    media="CD",
                    data_source="MusicBrainz",
                    album_id="id1",
                ),
            ],
            allowed_actions=[ImportAction.APPLY, ImportAction.ASIS, ImportAction.SKIP],
        )
    )

    response = await http_client.get(f"/fragment/import/{job.id}")
    assert response.status_code == 200
    html = response.text

    # Table with the differentiating columns; "Album" (same label) is not a column.
    assert "<table" in html
    for header in ("<th>Match</th>", "<th>Year</th>", "<th>Media</th>", "<th>Link</th>"):
        assert header in html
    assert "<th>Album</th>" not in html
    assert "2026" in html and "Digital Media" in html
    assert "https://musicbrainz.org/release/id0" in html

    # One Apply button per candidate, each carrying its own candidate_index.
    assert html.count('"action": "apply"') == 2
    assert '"candidate_index": 0' in html and '"candidate_index": 1' in html


@pytest.mark.anyio
async def test_job_fragment_renders_basename_summary_and_output(
    client_and_store: tuple[AsyncClient, ImportStore],
) -> None:
    http_client, store = client_and_store
    job = await store.create(["/music/incoming/Album X"])

    html = (await http_client.get(f"/fragment/import/{job.id}")).text

    assert "Album X" in html  # just the basename...
    assert "/music/incoming/Album X" not in html  # ...not the full path
    assert "Src Path:" not in html
    assert "Show import job output" not in html  # per-row label removed
    assert "pending" in html
    assert "(no output yet.)" in html  # the (collapsed) output pre is still present


@pytest.mark.anyio
async def test_active_list_shows_active_jobs_newest_first_and_hides_terminal(
    client_and_store: tuple[AsyncClient, ImportStore],
) -> None:
    http_client, store = client_and_store
    running = await store.create(["/m/RunAlbum"])
    await store.claim_next("worker-1")  # oldest PENDING -> RUNNING (the `running` job)
    pending = await store.create(["/m/PendAlbum"])  # stays PENDING
    done = await store.create(["/m/DoneAlbum"])
    await store.set_status(done.id, ImportJobStatus.COMPLETED)

    html = (await http_client.get("/fragment/import")).text

    # Active jobs are present; the terminal (completed) one is omitted.
    assert f'id="import-job-{running.id}"' in html
    assert f'id="import-job-{pending.id}"' in html
    assert f'id="import-job-{done.id}"' not in html
    # Newest first: the later-created PENDING job appears before the older RUNNING one.
    assert html.index(f'id="import-job-{pending.id}"') < html.index(f'id="import-job-{running.id}"')
    # Source shown as the basename only.
    assert "RunAlbum" in html and "PendAlbum" in html
    assert "Src Path:" not in html and "/m/RunAlbum" not in html


@pytest.mark.anyio
async def test_import_submit_creates_single_path_job(client_and_store: tuple[AsyncClient, ImportStore]) -> None:
    http_client, store = client_and_store
    response = await http_client.post("/fragment/import", data={"path": "  /downloads/Album Y  "})

    assert response.status_code == 200
    assert "Album Y" in response.text  # shown as basename (trimmed)
    assert "Src Path:" not in response.text
    jobs = await store.list()
    assert len(jobs) == 1
    assert jobs[0].paths == ["/downloads/Album Y"]  # full path still stored


@pytest.mark.anyio
async def test_import_submit_rejects_empty_path(client_and_store: tuple[AsyncClient, ImportStore]) -> None:
    http_client, _ = client_and_store
    response = await http_client.post("/fragment/import", data={"path": "   "})
    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("bad_path", ["/music/incoming/Album", "/etc/passwd", "/downloads/../etc", "relative/x"])
async def test_import_submit_rejects_path_outside_root(
    client_and_store: tuple[AsyncClient, ImportStore], bad_path: str
) -> None:
    http_client, store = client_and_store
    response = await http_client.post("/fragment/import", data={"path": bad_path})
    assert response.status_code == 422
    assert await store.list() == []  # nothing created


@pytest.mark.anyio
async def test_path_suggestions_lists_matching_subdirectories(
    client_and_store: tuple[AsyncClient, ImportStore], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    http_client, _ = client_and_store
    # Point the import root at a temp dir so the FS-backed suggestions are testable.
    monkeypatch.setattr(_import_fragments_mod, "_IMPORT_ROOT", str(tmp_path))
    for name in ("Boards of Canada", "Bonobo", "Aphex Twin"):
        (tmp_path / name).mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")  # a file: must be ignored

    # Trailing slash -> list everything in the (root) directory.
    listed = (await http_client.get("/fragment/import/path-suggestions", params={"path": f"{tmp_path}/"})).text
    assert f'value="{tmp_path}/Boards of Canada"' in listed
    assert f'value="{tmp_path}/Bonobo"' in listed
    assert f'value="{tmp_path}/Aphex Twin"' in listed
    assert "notes.txt" not in listed  # files are not suggested

    # A leaf prefix filters (case-insensitive) to matching folders only.
    filtered = (await http_client.get("/fragment/import/path-suggestions", params={"path": f"{tmp_path}/bo"})).text
    assert "Boards of Canada" in filtered and "Bonobo" in filtered
    assert "Aphex Twin" not in filtered


@pytest.mark.anyio
async def test_path_suggestions_empty_outside_import_root(
    client_and_store: tuple[AsyncClient, ImportStore], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    http_client, _ = client_and_store
    monkeypatch.setattr(_import_fragments_mod, "_IMPORT_ROOT", str(tmp_path))
    (tmp_path / "Album").mkdir()

    # Relative paths, paths outside the root, and `..` escapes all yield no suggestions.
    for path in ("relative/x", "/etc", "/downloads/Album", f"{tmp_path}/../etc"):
        body = (await http_client.get("/fragment/import/path-suggestions", params={"path": path})).text
        assert body.strip() == "", f"expected no suggestions for {path!r}"
