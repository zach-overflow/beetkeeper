"""Tests that the events-page HTML fragment renders the recently ingested beets events from the DB.

The `get_session` dependency is overridden onto a freshly-migrated temp DB; events are seeded through the
public `/api/events` endpoints (the same path the listener plugin uses), then the `/fragment/event` route is
asserted to render them. Runs fully in-process (no real DB server, no sockets).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.api.fastapi_app import beetkeeper_app
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


@pytest.mark.anyio
async def test_event_fragment_empty_when_no_events(client: AsyncClient) -> None:
    response = await client.get("/fragment/event")
    assert response.status_code == 200
    assert "No beets events" in response.text


@pytest.mark.anyio
async def test_event_fragment_renders_recent_events(client: AsyncClient) -> None:
    album_payload = {"event_type": "album_imported", "pushed_at": _pushed_at(), "album_fields": {"id": 101}}
    track_payload = {
        "event_type": "item_imported",
        "pushed_at": _pushed_at(),
        "album_fields": {"id": 101},
        "track_fields": {"id": 777},
    }
    assert (await client.post("/api/events/album", json=album_payload)).status_code == 201
    assert (await client.post("/api/events/track", json=track_payload)).status_code == 201

    response = await client.get("/fragment/event")
    assert response.status_code == 200
    body = response.text
    assert "album_imported" in body
    assert "item_imported" in body
    assert "101" in body  # the album id from both events
    assert "777" in body  # the track item id
    assert "2026-06-23" in body  # the formatted pushed_at timestamp
