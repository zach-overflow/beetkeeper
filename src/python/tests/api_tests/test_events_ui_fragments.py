"""Tests that the events-page HTML fragment renders the recently ingested beets events from the DB.

The `get_session` dependency is overridden onto a freshly-migrated temp DB (see this package's
`conftest.py`); events are seeded through the public `/api/events` endpoints (the same path the listener
plugin uses), then the `/fragment/event` route is asserted to render them.
"""

import pytest
from httpx import AsyncClient

from beetkeeper.db.session import get_session

from .conftest import DependencyOverrides, SessionOverride


@pytest.fixture
def app_dependency_overrides(get_session_override: SessionOverride) -> DependencyOverrides:
    return {get_session: get_session_override}


@pytest.mark.anyio
async def test_event_fragment_empty_when_no_events(client: AsyncClient) -> None:
    response = await client.get("/fragment/event")
    assert response.status_code == 200
    assert "No beets events" in response.text


@pytest.mark.anyio
async def test_event_fragment_renders_recent_events(client: AsyncClient, pushed_at: str) -> None:
    album_payload = {"event_type": "album_imported", "pushed_at": pushed_at, "album_fields": {"id": 101}}
    track_payload = {
        "event_type": "item_imported",
        "pushed_at": pushed_at,
        "track_fields": {"id": 777, "album_id": 101},
    }
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201
    assert (await client.post("/api/events/track", json=track_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert "album_imported" in body
    assert "item_imported" in body
    assert "101" in body
    assert "777" in body
    assert "2026-06-23" in body


@pytest.mark.anyio
async def test_event_fragment_renders_filesystem_event_paths(client: AsyncClient, pushed_at: str) -> None:
    """An `import_task_files` event's source and destination filepaths render alongside the event row."""
    fs_payload = {
        "event_type": "import_task_files",
        "pushed_at": pushed_at,
        "choice_flag": "APPLY",
        "source_paths": ["/inbox/An Album"],
        "imported_items": [
            {
                "event_type": "import_task_files",
                "pushed_at": pushed_at,
                "track_fields": {"id": 11, "album_id": 90, "path": f"/music/An Album/{track:02d} song.mp3"},
            }
            for track in (1, 2)
        ],
    }
    assert (await client.post("/api/events/filesystem", json=fs_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert "Source path(s)" in body
    assert "Destination path(s)" in body
    assert "/inbox/An Album" in body
    assert "/music/An Album/01 song.mp3" in body
    assert "/music/An Album/02 song.mp3" in body
