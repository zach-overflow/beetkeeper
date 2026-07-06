"""Tests for the `/api/import` JSON routes, backed by a real `ImportStore` over a migrated temp DB.

`get_import_store` is overridden with a store bound to the test sessionmaker (no import worker runs; see
this package's `conftest.py`), so these cover submit/list/get/decision/abort against actual persisted rows.
"""

import pytest
from httpx import AsyncClient

from beetkeeper.api.dependencies import get_import_store
from beetkeeper.core import ImportStore

from .conftest import DependencyOverrides


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
async def test_list_imports_returns_submitted_jobs(client: AsyncClient) -> None:
    await client.post("/api/import", json={"paths": ["/m/1"]})
    await client.post("/api/import", json={"paths": ["/m/2"]})
    response = await client.get("/api/import")
    assert response.status_code == 200
    assert len(response.json()) == 2


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
