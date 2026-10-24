"""Direct tests of `listener_event_records_lookup` against a migrated temp DB (no HTTP layer)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.api.adapters import listener_event_records_lookup
from beetkeeper.api.api_models import EventSubjectSummary
from beetkeeper.constants import BeetsEventType
from beetkeeper.db.models import AlbumEvent, ImportDestinationPath, ImportSourcePath, ListenerEvent, TrackEvent

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)


async def _insert_listener_event(session: AsyncSession, event_type: BeetsEventType, pushed_at: datetime) -> int:
    event = ListenerEvent(event_type=event_type, pushed_at=pushed_at)
    session.add(event)
    await session.flush()
    assert event.event_id is not None
    return event.event_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    "event_type", [BeetsEventType.ALBUM_IMPORTED, BeetsEventType.TRACK_IMPORTED, BeetsEventType.IMPORT_TASK_FILES]
)
async def test_event_without_child_rows_yields_empty_lists(
    session_factory: async_sessionmaker[AsyncSession], event_type: BeetsEventType
) -> None:
    async with session_factory() as session:
        await _insert_listener_event(session, event_type, _BASE_TIME)
        await session.commit()

    async with session_factory() as session:
        records = await listener_event_records_lookup(session=session, offset=0, limit=10)

    assert len(records) == 1
    record = records[0]
    assert record.event_type is event_type
    assert record.pushed_at == _BASE_TIME
    assert record.albums == []
    assert record.tracks == []
    assert record.source_paths == []
    assert record.destination_paths == []


@pytest.mark.anyio
async def test_import_task_files_event_derives_releases_and_paths(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        event_id = await _insert_listener_event(session, BeetsEventType.IMPORT_TASK_FILES, _BASE_TIME)
        session.add_all(
            [
                TrackEvent(
                    listener_event_id=event_id,
                    beets_item_id=1,
                    beets_album_id=90,
                    track_title="One",
                    album_name="An Album",
                ),
                TrackEvent(
                    listener_event_id=event_id,
                    beets_item_id=2,
                    beets_album_id=90,
                    track_title="Two",
                    album_name="An Album",
                ),
                TrackEvent(
                    listener_event_id=event_id,
                    beets_item_id=3,
                    beets_album_id=90,
                    track_title="Three",
                    album_name="An Album",
                ),
                TrackEvent(listener_event_id=event_id, beets_item_id=4, track_title="Loose"),
                ImportSourcePath(listener_event_id=event_id, source_path="/downloads/an-album"),
                ImportDestinationPath(listener_event_id=event_id, destination_path="/music/An Album/01 One.flac"),
                ImportDestinationPath(listener_event_id=event_id, destination_path="/music/An Album/02 Two.flac"),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        records = await listener_event_records_lookup(session=session, offset=0, limit=10)

    assert len(records) == 1
    record = records[0]
    assert record.albums == [EventSubjectSummary(beets_id=90, name="An Album")]
    assert record.tracks == [
        EventSubjectSummary(beets_id=1, name="One"),
        EventSubjectSummary(beets_id=2, name="Two"),
        EventSubjectSummary(beets_id=3, name="Three"),
        EventSubjectSummary(beets_id=4, name="Loose"),
    ]
    assert record.source_paths == ["/downloads/an-album"]
    assert record.destination_paths == ["/music/An Album/01 One.flac", "/music/An Album/02 Two.flac"]


@pytest.mark.anyio
@pytest.mark.parametrize(("offset", "limit", "expected_album_ids"), [(0, 2, [[3], [2]]), (2, 2, [[1]]), (4, 2, [])])
async def test_listing_is_paginated_newest_first(
    session_factory: async_sessionmaker[AsyncSession], offset: int, limit: int, expected_album_ids: list[list[int]]
) -> None:
    async with session_factory() as session:
        for album_id in (1, 2, 3):
            pushed_at = _BASE_TIME + timedelta(minutes=album_id)
            event_id = await _insert_listener_event(session, BeetsEventType.ALBUM_IMPORTED, pushed_at)
            session.add(AlbumEvent(listener_event_id=event_id, beets_album_id=album_id, album_name=f"Album {album_id}"))
        await session.commit()

    async with session_factory() as session:
        records = await listener_event_records_lookup(session=session, offset=offset, limit=limit)

    assert [record.album_ids for record in records] == expected_album_ids
