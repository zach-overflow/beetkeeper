"""Renders the import job HTMX fragment for a job awaiting a decision, asserting the candidate table HTML.

Backed by a real `ImportStore` over a migrated temp DB (no import worker runs; see this package's
`conftest.py`); this exercises the full `import_job.html` template, so it also guards against Jinja errors
in the candidate-table markup.
"""

import importlib
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from beetkeeper.api.dependencies import get_import_store
from beetkeeper.core import ImportJobStatus, ImportStore
from beetkeeper.core.import_jobs import DecisionRequest, ImportAction, ImportCandidate

from .conftest import DependencyOverrides

# importlib because the `ui_routes` package re-exports the router under this name, shadowing the submodule.
_import_fragments_mod = importlib.import_module("beetkeeper.api.ui_routes.import_ui_fragments_router")


@pytest.fixture
def app_dependency_overrides(import_store: ImportStore) -> DependencyOverrides:
    return {get_import_store: lambda: import_store}


@pytest.mark.anyio
async def test_decision_fragment_renders_candidate_table(client: AsyncClient, import_store: ImportStore) -> None:
    job = await import_store.create(["/m/a"])
    await import_store.set_awaiting(
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

    response = await client.get(f"/fragment/import/{job.id}")
    assert response.status_code == 200
    html = response.text

    assert "<table" in html
    for header in ("<th>Match</th>", "<th>Year</th>", "<th>Media</th>", "<th>Link</th>"):
        assert header in html
    assert "<th>Album</th>" not in html
    assert "2026" in html and "Digital Media" in html
    assert "https://musicbrainz.org/release/id0" in html

    assert html.count('"action": "apply"') == 2
    assert '"candidate_index": 0' in html and '"candidate_index": 1' in html


@pytest.mark.anyio
async def test_job_fragment_renders_basename_summary_and_output(client: AsyncClient, import_store: ImportStore) -> None:
    job = await import_store.create(["/music/incoming/Album X"])

    html = (await client.get(f"/fragment/import/{job.id}")).text

    assert "Album X" in html
    assert "/music/incoming/Album X" not in html
    assert "Src Path:" not in html
    assert "Show import job output" not in html
    assert "pending" in html
    assert "(no output yet.)" in html


@pytest.mark.anyio
async def test_active_list_shows_active_jobs_newest_first_and_hides_terminal(
    client: AsyncClient, import_store: ImportStore
) -> None:
    running = await import_store.create(["/m/RunAlbum"])
    await import_store.claim_next("worker-1")
    pending = await import_store.create(["/m/PendAlbum"])
    done = await import_store.create(["/m/DoneAlbum"])
    await import_store.set_status(done.id, ImportJobStatus.COMPLETED)

    html = (await client.get("/fragment/import")).text

    assert f'id="import-job-{running.id}"' in html
    assert f'id="import-job-{pending.id}"' in html
    assert f'id="import-job-{done.id}"' not in html
    assert html.index(f'id="import-job-{pending.id}"') < html.index(f'id="import-job-{running.id}"')
    assert "RunAlbum" in html and "PendAlbum" in html
    assert "Src Path:" not in html and "/m/RunAlbum" not in html


@pytest.mark.anyio
async def test_import_submit_creates_single_path_job(client: AsyncClient, import_store: ImportStore) -> None:
    response = await client.post("/fragment/import", data={"path": "  /downloads/Album Y  "})

    assert response.status_code == 200
    assert "Album Y" in response.text
    assert "Src Path:" not in response.text
    jobs = await import_store.list()
    assert len(jobs) == 1
    assert jobs[0].paths == ["/downloads/Album Y"]


@pytest.mark.anyio
async def test_import_submit_records_options(client: AsyncClient, import_store: ImportStore) -> None:
    response = await client.post(
        "/fragment/import",
        data={
            "path": "/downloads/Album Z",
            "quiet": "on",
            "group_albums": "on",
            "flat": "on",
            "logpath": "  /logs/import.log  ",
            "set_fields": "genre=Jazz\n\n comments = late night ",
        },
    )
    assert response.status_code == 200
    assert "options:" in response.text
    for label in ("quiet", "group albums", "flat", "log: /logs/import.log", "genre=Jazz", "comments=late night"):
        assert label in response.text
    (job,) = await import_store.list()
    assert job.quiet is True and job.group_albums is True and job.flat is True
    assert job.logpath == "/logs/import.log"
    assert job.set_fields == {"genre": "Jazz", "comments": "late night"}


@pytest.mark.anyio
async def test_import_submit_without_options_leaves_settings_unset(
    client: AsyncClient, import_store: ImportStore
) -> None:
    response = await client.post("/fragment/import", data={"path": "/downloads/Album Y"})
    assert response.status_code == 200
    assert "options:" not in response.text
    (job,) = await import_store.list()
    assert job.quiet is False and job.group_albums is False and job.flat is False
    assert job.logpath is None
    assert job.set_fields == {}


@pytest.mark.anyio
@pytest.mark.parametrize("bad_set_fields", ["genre Jazz", "=Jazz", "genre=Jazz\nnot a pair"])
async def test_import_submit_rejects_malformed_set_fields(
    client: AsyncClient, import_store: ImportStore, bad_set_fields: str
) -> None:
    response = await client.post("/fragment/import", data={"path": "/downloads/Album", "set_fields": bad_set_fields})
    assert response.status_code == 422
    assert await import_store.list() == []


@pytest.mark.anyio
async def test_import_page_prefills_options_from_beets_config(
    client: AsyncClient, beets_import_config: Any, tmp_path: Path
) -> None:
    beets_import_config["quiet"] = True
    beets_import_config["group_albums"] = True
    beets_import_config["log"] = str(tmp_path / "import.log")
    beets_import_config["set_fields"] = {"genre": "Jazz"}

    html = (await client.get("/import")).text

    assert 'name="quiet" checked' in html
    assert 'name="group_albums" checked' in html
    assert 'name="flat"' in html and 'name="flat" checked' not in html
    assert f'value="{tmp_path}/import.log"' in html
    assert "genre=Jazz</textarea>" in html


@pytest.mark.anyio
async def test_import_page_defaults_to_unchecked_options(client: AsyncClient) -> None:
    html = (await client.get("/import")).text
    for name in ("quiet", "group_albums", "flat"):
        assert f'name="{name}"' in html
        assert f'name="{name}" checked' not in html
    assert 'name="logpath"' in html and 'value=""' in html
    assert 'name="set_fields"' in html


@pytest.mark.anyio
async def test_import_submit_rejects_empty_path(client: AsyncClient) -> None:
    response = await client.post("/fragment/import", data={"path": "   "})
    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("bad_path", ["/music/incoming/Album", "/etc/passwd", "/downloads/../etc", "relative/x"])
async def test_import_submit_rejects_path_outside_root(
    client: AsyncClient, import_store: ImportStore, bad_path: str
) -> None:
    response = await client.post("/fragment/import", data={"path": bad_path})
    assert response.status_code == 422
    assert await import_store.list() == []


@pytest.mark.anyio
async def test_path_suggestions_lists_matching_subdirectories(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_import_fragments_mod, "_IMPORT_ROOT", str(tmp_path))
    for name in ("Boards of Canada", "Bonobo", "Aphex Twin"):
        (tmp_path / name).mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    listed = (await client.get("/fragment/import/path-suggestions", params={"path": f"{tmp_path}/"})).text
    assert f'value="{tmp_path}/Boards of Canada"' in listed
    assert f'value="{tmp_path}/Bonobo"' in listed
    assert f'value="{tmp_path}/Aphex Twin"' in listed
    assert "notes.txt" not in listed

    filtered = (await client.get("/fragment/import/path-suggestions", params={"path": f"{tmp_path}/bo"})).text
    assert "Boards of Canada" in filtered and "Bonobo" in filtered
    assert "Aphex Twin" not in filtered


@pytest.mark.anyio
async def test_path_suggestions_empty_outside_import_root(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_import_fragments_mod, "_IMPORT_ROOT", str(tmp_path))
    (tmp_path / "Album").mkdir()

    for path in ("relative/x", "/etc", "/downloads/Album", f"{tmp_path}/../etc"):
        body = (await client.get("/fragment/import/path-suggestions", params={"path": path})).text
        assert body.strip() == "", f"expected no suggestions for {path!r}"
