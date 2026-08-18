"""Tests that the events-page HTML fragment renders the recently ingested beets events from the DB.

The `get_session` dependency is overridden onto a freshly-migrated temp DB (see this package's
`conftest.py`); events are seeded through the public `/api/events` endpoints (the same path the listener
plugin uses), then the `/fragment/event` route is asserted to render them.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from beetkeeper.db.session import get_session

from .conftest import DependencyOverrides, SessionOverride


@pytest.fixture
def app_dependency_overrides(get_session_override: SessionOverride) -> DependencyOverrides:
    return {get_session: get_session_override}


def _album_import_payloads(
    fs_pushed_at: str, album_pushed_at: str, beets_album_id: int | None
) -> tuple[dict[str, object], dict[str, object]]:
    """An album import's `import_task_files` + `album_imported` push pair (album id 101, tracks 11 and 12)."""
    fs_payload: dict[str, object] = {
        "event_type": "import_task_files",
        "pushed_at": fs_pushed_at,
        "choice_flag": "APPLY",
        "source_paths": ["/inbox/An Album"],
        "imported_items": [
            {
                "event_type": "import_task_files",
                "pushed_at": fs_pushed_at,
                "track_fields": {
                    "id": track_id,
                    "album_id": beets_album_id,
                    "path": f"/music/An Album/{index:02d} song.mp3",
                    "title": f"Song {index}",
                    "album": "An Album",
                },
            }
            for index, track_id in enumerate((11, 12), start=1)
        ],
    }
    album_payload: dict[str, object] = {
        "event_type": "album_imported",
        "pushed_at": album_pushed_at,
        "album_fields": {"id": 101, "album": "An Album"},
    }
    return fs_payload, album_payload


@pytest.mark.anyio
async def test_event_fragment_empty_when_no_events(client: AsyncClient) -> None:
    response = await client.get("/fragment/event")
    assert response.status_code == 200
    assert "No beets events" in response.text


@pytest.mark.anyio
async def test_event_fragment_renders_recent_events(client: AsyncClient, pushed_at: str) -> None:
    """The release/track cells show the recorded names, expandable to the subjects' beets ids."""
    album_payload = {
        "event_type": "album_imported",
        "pushed_at": pushed_at,
        "album_fields": {"id": 101, "album": "An Album"},
    }
    track_payload = {
        "event_type": "item_imported",
        "pushed_at": pushed_at,
        "track_fields": {"id": 777, "album_id": 101, "title": "A Song"},
    }
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201
    assert (await client.post("/api/events/track", json=track_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert "Release Name" in body
    assert "Track names" in body
    assert "album_imported" in body
    assert "item_imported" in body
    assert "<summary>An Album</summary>" in body
    assert "<summary>A Song</summary>" in body
    assert "beets album id: <code>101</code>" in body
    assert "beets track id: <code>777</code>" in body
    assert "2026-06-23" in body


@pytest.mark.anyio
async def test_event_fragment_falls_back_to_ids_for_nameless_events(client: AsyncClient, pushed_at: str) -> None:
    """Rows ingested without names (e.g. before names were recorded) show the beets ids instead."""
    album_payload = {"event_type": "album_imported", "pushed_at": pushed_at, "album_fields": {"id": 101}}
    track_payload = {"event_type": "item_imported", "pushed_at": pushed_at, "track_fields": {"id": 777}}
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201
    assert (await client.post("/api/events/track", json=track_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert "<summary>101</summary>" in body
    assert "<summary>777</summary>" in body


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


@pytest.mark.anyio
async def test_event_fragment_merges_album_import_push_pair(client: AsyncClient, pushed_at: str) -> None:
    """An album import's back-to-back `import_task_files` + `album_imported` pushes render as one
    "Album imported" row carrying the release name, the imported tracks, and the source/destination paths."""
    fs_payload, album_payload = _album_import_payloads(pushed_at, pushed_at, beets_album_id=101)
    assert (await client.post("/api/events/filesystem", json=fs_payload)).status_code == 201
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert body.count("<tr>") == 2
    assert "Album imported" in body
    assert "import_task_files" not in body
    assert "album_imported" not in body
    assert "<summary>An Album</summary>" in body
    assert "beets album id: <code>101</code>" in body
    assert "<summary>Song 1, Song 2</summary>" in body
    assert "beets track id: <code>11</code>" in body
    assert "beets track id: <code>12</code>" in body
    assert "/inbox/An Album" in body
    assert "/music/An Album/01 song.mp3" in body
    assert "/music/An Album/02 song.mp3" in body


@pytest.mark.anyio
async def test_event_fragment_merges_singleton_import_push_pair(client: AsyncClient, pushed_at: str) -> None:
    """A singleton import's back-to-back `import_task_files` + `item_imported` pushes render as one
    "Singleton imported" row carrying the track title, the singleton's release name (which has no beets
    album id), and the source/destination paths."""
    fs_payload = {
        "event_type": "import_task_files",
        "pushed_at": pushed_at,
        "choice_flag": "APPLY",
        "source_paths": ["/inbox/loose song.mp3"],
        "imported_items": [
            {
                "event_type": "import_task_files",
                "pushed_at": pushed_at,
                "track_fields": {
                    "id": 21,
                    "album_id": None,
                    "path": "/music/loose song.mp3",
                    "title": "Loose Song",
                    "album": "Loose Release",
                },
            }
        ],
    }
    track_payload = {
        "event_type": "item_imported",
        "pushed_at": pushed_at,
        "track_fields": {"id": 21, "title": "Loose Song", "album": "Loose Release"},
    }
    assert (await client.post("/api/events/filesystem", json=fs_payload)).status_code == 201
    assert (await client.post("/api/events/track", json=track_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert body.count("<tr>") == 2
    assert "Singleton imported" in body
    assert "import_task_files" not in body
    assert "item_imported" not in body
    assert "<summary>Loose Release</summary>" in body
    assert "beets album id: <code>—</code>" in body
    assert "<summary>Loose Song</summary>" in body
    assert "beets track id: <code>21</code>" in body
    assert "/inbox/loose song.mp3" in body
    assert "/music/loose song.mp3" in body


@pytest.mark.anyio
async def test_event_fragment_keeps_unrelated_push_rows_unmerged(client: AsyncClient, pushed_at: str) -> None:
    """An `import_task_files` push with no album association never folds into an `album_imported` row,
    even when both land back-to-back; unmerged rows keep their raw event-type labels."""
    fs_payload, album_payload = _album_import_payloads(pushed_at, pushed_at, beets_album_id=None)
    assert (await client.post("/api/events/filesystem", json=fs_payload)).status_code == 201
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert body.count("<tr>") == 3
    assert "import_task_files" in body
    assert "album_imported" in body


@pytest.mark.anyio
async def test_event_fragment_keeps_distant_same_album_rows_unmerged(client: AsyncClient) -> None:
    """A same-album `import_task_files` from a much earlier import (e.g. its `album_imported` push failed)
    does not pair with a later `album_imported` — merging is bounded to near-simultaneous pushes."""
    fs_pushed_at = datetime(2026, 6, 23, 10, 0, 0, tzinfo=UTC).isoformat()
    album_pushed_at = datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC).isoformat()
    fs_payload, album_payload = _album_import_payloads(fs_pushed_at, album_pushed_at, beets_album_id=101)
    assert (await client.post("/api/events/filesystem", json=fs_payload)).status_code == 201
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert body.count("<tr>") == 3
    assert "import_task_files" in body
    assert "album_imported" in body
