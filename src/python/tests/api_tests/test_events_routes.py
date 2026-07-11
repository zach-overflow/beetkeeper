"""Tests that the `/api/events` endpoints persist the expected rows and return the expected payloads.

The `get_session` dependency is overridden to draw sessions from a freshly-migrated temp DB (see this
package's `conftest.py`), so these run fully in-process (no real DB server, no sockets).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import get_session

from .conftest import DependencyOverrides, SessionOverride


@pytest.fixture
def app_dependency_overrides(get_session_override: SessionOverride) -> DependencyOverrides:
    return {get_session: get_session_override}


def _track_item(pushed_at: str, beets_item_id: int, beets_album_id: int | None = 1) -> dict[str, object]:
    return {
        "event_type": "item_imported",
        "pushed_at": pushed_at,
        "track_fields": {"id": beets_item_id, "album_id": beets_album_id},
    }


@pytest.mark.anyio
async def test_album_event_persists(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], pushed_at: str
) -> None:
    payload = {"event_type": "album_imported", "pushed_at": pushed_at, "album_fields": {"id": 101}}
    response = await client.post("/api/events/album", json=payload)

    assert response.status_code == 201
    assert response.json() == {"event_type": "album_imported", "ingested_id": 101, "error_msg": None}

    async with session_factory() as session:
        listeners = (await session.execute(select(ListenerEvent))).scalars().all()
        albums = (await session.execute(select(AlbumEvent))).scalars().all()
    assert len(listeners) == 1
    assert listeners[0].event_type == "album_imported"
    assert len(albums) == 1
    assert albums[0].beets_album_id == 101
    assert albums[0].listener_event_id == listeners[0].event_id


@pytest.mark.anyio
async def test_track_event_persists(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], pushed_at: str
) -> None:
    response = await client.post("/api/events/track", json=_track_item(pushed_at, 777, beets_album_id=55))

    assert response.status_code == 201
    assert response.json()["ingested_id"] == 777

    async with session_factory() as session:
        tracks = (await session.execute(select(TrackEvent))).scalars().all()
    assert len(tracks) == 1
    assert tracks[0].beets_item_id == 777
    assert tracks[0].beets_album_id == 55


@pytest.mark.anyio
async def test_singleton_track_event_persists_without_album(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], pushed_at: str
) -> None:
    """A singleton import (no album association) is a valid track event with a NULL `beets_album_id`."""
    response = await client.post("/api/events/track", json=_track_item(pushed_at, 888, beets_album_id=None))

    assert response.status_code == 201
    assert response.json()["ingested_id"] == 888

    async with session_factory() as session:
        tracks = (await session.execute(select(TrackEvent))).scalars().all()
    assert len(tracks) == 1
    assert tracks[0].beets_album_id is None


@pytest.mark.anyio
async def test_filesystem_event_persists_each_item(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], pushed_at: str
) -> None:
    payload = {
        "event_type": "import_task_files",
        "pushed_at": pushed_at,
        "choice_flag": "APPLY",
        "imported_items": [
            _track_item(pushed_at, 11, 90),
            _track_item(pushed_at, 12, 90),
            _track_item(pushed_at, 13, 90),
        ],
    }
    response = await client.post("/api/events/filesystem", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["event_type"] == "import_task_files"
    assert [r["ingested_id"] for r in body["event_ingest_responses"]] == [11, 12, 13]

    async with session_factory() as session:
        listeners = (await session.execute(select(ListenerEvent))).scalars().all()
        tracks = (await session.execute(select(TrackEvent))).scalars().all()
    assert len(listeners) == 1
    assert sorted(t.beets_item_id for t in tracks) == [11, 12, 13]
    assert {t.beets_album_id for t in tracks} == {90}


@pytest.mark.anyio
async def test_album_event_rejects_unknown_event_type(client: AsyncClient, pushed_at: str) -> None:
    payload = {"event_type": "not_a_real_event", "pushed_at": pushed_at, "album_fields": {"id": 1}}
    response = await client.post("/api/events/album", json=payload)
    assert response.status_code == 422


@pytest.mark.anyio
async def test_events_listing_empty(client: AsyncClient) -> None:
    response = await client.get("/api/events")
    assert response.status_code == 200
    assert response.json() == {"events": []}


@pytest.mark.anyio
async def test_events_listing_returns_recent_events_with_child_ids(client: AsyncClient, pushed_at: str) -> None:
    """The listing returns ingested events newest-first, each with its child beets album/track ids."""
    album_payload = {"event_type": "album_imported", "pushed_at": pushed_at, "album_fields": {"id": 101}}
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201
    assert (
        await client.post("/api/events/track", json=_track_item(pushed_at, 777, beets_album_id=101))
    ).status_code == 201

    response = await client.get("/api/events")
    assert response.status_code == 200
    events = response.json()["events"]
    assert [e["event_type"] for e in events] == ["item_imported", "album_imported"]
    assert events[0]["track_ids"] == [777]
    assert events[0]["album_ids"] == []
    assert events[1]["album_ids"] == [101]
    assert events[1]["track_ids"] == []


@pytest.mark.anyio
async def test_events_listing_respects_limit(client: AsyncClient, pushed_at: str) -> None:
    for beets_album_id in (1, 2, 3):
        payload = {"event_type": "album_imported", "pushed_at": pushed_at, "album_fields": {"id": beets_album_id}}
        assert (await client.post("/api/events/album", json=payload)).status_code == 201

    response = await client.get("/api/events", params={"limit": 2})
    assert response.status_code == 200
    events = response.json()["events"]
    assert [e["album_ids"] for e in events] == [[3], [2]]

    assert (await client.get("/api/events", params={"limit": 0})).status_code == 422
