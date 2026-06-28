"""Async ORM-behavior tests against a freshly-migrated temp SQLite DB (see `db_tests/conftest.py`).

These exercise the async session wiring in `beetkeeper.db.session`, including the per-connection
`PRAGMA foreign_keys=ON` that makes the ON DELETE CASCADE relationships behave.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from beetkeeper.db.models import AlbumEvent, ListenerEvent


async def _insert_listener_event(session: AsyncSession, event_type: str) -> ListenerEvent:
    event = ListenerEvent(event_type=event_type, pushed_at=datetime.now(UTC))
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@pytest.mark.anyio
async def test_insert_and_read_back_child_event(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        parent = await _insert_listener_event(session, "album_imported")
        assert parent.event_id is not None
        session.add(AlbumEvent(listener_event_id=parent.event_id, beets_album_id=42))
        await session.commit()

    async with session_factory() as session:
        rows = (await session.execute(select(AlbumEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].beets_album_id == 42
    assert rows[0].listener_event_id == parent.event_id


@pytest.mark.anyio
async def test_on_delete_cascade_removes_children(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        parent = await _insert_listener_event(session, "album_removed")
        session.add(AlbumEvent(listener_event_id=parent.event_id, beets_album_id=7))
        await session.commit()

    async with session_factory() as session:
        # Deleting the parent row should cascade to the child via the DB-level FK (requires FK pragma ON).
        parent_to_delete = (await session.execute(select(ListenerEvent))).scalars().one()
        await session.delete(parent_to_delete)
        await session.commit()

    async with session_factory() as session:
        remaining = (await session.execute(select(AlbumEvent))).scalars().all()
    assert remaining == []


@pytest.mark.anyio
async def test_foreign_key_violation_is_rejected(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        session.add(AlbumEvent(listener_event_id=999_999, beets_album_id=1))
        with pytest.raises(IntegrityError):
            await session.commit()
