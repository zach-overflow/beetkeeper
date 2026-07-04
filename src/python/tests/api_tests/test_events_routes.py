"""Tests that the `/api/events` endpoints persist the expected rows and return the expected payloads.

The `get_session` dependency is overridden to draw sessions from a freshly-migrated temp DB, so these run
fully in-process (no real DB server, no sockets). The async client follows FastAPI's async-test guidance.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from beetkeeper.api.fastapi_app import beetkeeper_app
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import get_session


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    """An ASGI-transport client whose `get_session` dependency is bound to the migrated temp DB."""

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    beetkeeper_app.dependency_overrides[get_session] = _override_get_session
    try:
        transport = ASGITransport(app=beetkeeper_app)
        async with AsyncClient(transport=transport, base_url="http://testclient") as http_client:
            yield http_client
    finally:
        beetkeeper_app.dependency_overrides.clear()


def _pushed_at() -> str:
    return datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC).isoformat()


def _track_item(beets_item_id: int, beets_album_id: int = 1) -> dict[str, object]:
    return {
        "event_type": "item_imported",
        "pushed_at": _pushed_at(),
        "album_fields": {"id": beets_album_id},
        "track_fields": {"id": beets_item_id},
    }


@pytest.mark.anyio
async def test_album_event_persists(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    payload = {"event_type": "album_imported", "pushed_at": _pushed_at(), "album_fields": {"id": 101}}
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
async def test_track_event_persists(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    response = await client.post("/api/events/track", json=_track_item(777, beets_album_id=55))

    assert response.status_code == 201
    assert response.json()["ingested_id"] == 777

    async with session_factory() as session:
        tracks = (await session.execute(select(TrackEvent))).scalars().all()
    assert len(tracks) == 1
    assert tracks[0].beets_item_id == 777
    assert tracks[0].beets_album_id == 55


@pytest.mark.anyio
async def test_filesystem_event_persists_each_item(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    payload = {
        "event_type": "import_task_files",
        "pushed_at": _pushed_at(),
        "choice_flag": "APPLY",
        "imported_items": [_track_item(11, 90), _track_item(12, 90), _track_item(13, 90)],
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
async def test_album_event_rejects_unknown_event_type(client: AsyncClient) -> None:
    payload = {"event_type": "not_a_real_event", "pushed_at": _pushed_at(), "album_fields": {"id": 1}}
    response = await client.post("/api/events/album", json=payload)
    assert response.status_code == 422
