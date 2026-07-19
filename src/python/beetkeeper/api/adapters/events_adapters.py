from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnElement
from sqlmodel import col

from beetkeeper.api.api_models import APIAlbum, APITrack, EventSearchResult, ListenerEventDetails
from beetkeeper.api.constants import EventLookupEntityType
from beetkeeper.constants import BeetsEventType
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent

if TYPE_CHECKING:
    from beetkeeper.core.library import BeetsLibrary


# TODO[https://github.com/zach-overflow/beetkeeper/issues/75]: Add async, non-blocking logging here.
async def listener_event_records_lookup(session: AsyncSession, offset: int, limit: int) -> list[ListenerEventDetails]:
    """
    Queries the `beetkeeper` events table ordered from newest to oldest. This is the underlying bridge between
    the beetkeeper UI / API surfacing `beetsplug.beetkeeper_plugin` events information pushed from the
    `beetsplug.beetkeeper_plugin` event listener.
    """
    recent_events = (
        (
            await session.execute(
                select(ListenerEvent)
                .order_by(col(ListenerEvent.pushed_at).desc(), col(ListenerEvent.event_id).desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    event_ids = [event.event_id for event in recent_events]
    album_ids_by_event: dict[int | None, list[int]] = defaultdict(list)
    track_ids_by_event: dict[int | None, list[int]] = defaultdict(list)
    if event_ids:
        album_events = (
            (await session.execute(select(AlbumEvent).where(col(AlbumEvent.listener_event_id).in_(event_ids))))
            .scalars()
            .all()
        )
        for album_event in album_events:
            album_ids_by_event[album_event.listener_event_id].append(album_event.beets_album_id)
        track_events = (
            (await session.execute(select(TrackEvent).where(col(TrackEvent.listener_event_id).in_(event_ids))))
            .scalars()
            .all()
        )
        for track_event in track_events:
            track_ids_by_event[track_event.listener_event_id].append(track_event.beets_item_id)
    return [
        ListenerEventDetails(
            event_type=BeetsEventType(event.event_type),
            pushed_at=event.pushed_at,
            album_ids=album_ids_by_event.get(event.event_id, []),
            track_ids=track_ids_by_event.get(event.event_id, []),
        )
        for event in recent_events
    ]


def _defined_fields(subject_dict: dict[str, Any]) -> dict[str, Any]:
    """Drop null fields from a beets library dict so `APIAlbum`/`APITrack` field defaults apply.

    The generated models type some fields from beets' shipped defaults (e.g. `artpath: bytes`), but a real
    library row can hold NULL there — validating None would fail where omitting the key does not.
    """
    return {key: value for key, value in subject_dict.items() if value is not None}


async def _query_listener_event_join(
    session: AsyncSession,
    beets_library: BeetsLibrary,
    join_events_table: type[AlbumEvent] | type[TrackEvent],
    conditions: Sequence[ColumnElement[bool]],
    offset: int = 0,
    limit: int | None = None,
) -> list[EventSearchResult]:
    """
    Helper for running a JOIN query between `ListenerEvent` and one of its child tables for event search.

    Each matched `(child event, listener event)` row becomes one `EventSearchResult` (newest first). The
    matched beets album/item ids are looked up in the beets library in one batch; ids with no match yield
    a null `current_beets_subject_state` (the subject no longer exists in the beets library).
    """
    rows = (
        await session.execute(
            select(join_events_table, ListenerEvent)
            .join(ListenerEvent)
            .where(*conditions)
            .order_by(col(ListenerEvent.pushed_at).desc(), col(ListenerEvent.event_id).desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    if not rows:
        return []
    subject_models: dict[int, APIAlbum | APITrack]
    if join_events_table is AlbumEvent:
        beets_ids = [child_event.beets_album_id for child_event, _ in rows]
        album_dicts = await beets_library.get_albums(beets_ids)
        subject_models = {
            beets_id: APIAlbum(**_defined_fields(album_dict)) for beets_id, album_dict in album_dicts.items()
        }
    else:
        beets_ids = [child_event.beets_item_id for child_event, _ in rows]
        track_dicts = await beets_library.get_tracks(beets_ids)
        subject_models = {
            beets_id: APITrack(**_defined_fields(track_dict)) for beets_id, track_dict in track_dicts.items()
        }
    return [
        EventSearchResult(
            event_id=cast("int", listener_event.event_id),
            event_type=BeetsEventType(listener_event.event_type),
            event_time=listener_event.pushed_at,
            beets_id=beets_id,
            current_beets_subject_state=subject_models.get(beets_id),
        )
        for (_, listener_event), beets_id in zip(rows, beets_ids, strict=True)
    ]


async def listener_event_lookup_by_type_and_id(
    entity_type: EventLookupEntityType,
    entity_id: int,
    session: AsyncSession,
    offset: int,
    limit: int,
    beets_library: BeetsLibrary,
) -> list[EventSearchResult]:
    """
    Queries and returns the list of beetkeeper events associated with the provided ID, if any exist. This coroutine is
    generalized to handle the various similar `GET /events/{type}/{ID}` beetkeeper route handlers. In other words, this
    needs to support lookups by Beetkeeper event ID, beets album ID, or beets item ID (all mutually exclusive).
    """
    if entity_type is EventLookupEntityType.ALBUM:
        return await _query_listener_event_join(
            session=session,
            beets_library=beets_library,
            join_events_table=AlbumEvent,
            conditions=[col(AlbumEvent.beets_album_id) == entity_id],
            offset=offset,
            limit=limit,
        )
    if entity_type is EventLookupEntityType.TRACK:
        return await _query_listener_event_join(
            session=session,
            beets_library=beets_library,
            join_events_table=TrackEvent,
            conditions=[col(TrackEvent.beets_item_id) == entity_id],
            offset=offset,
            limit=limit,
        )
    # BKEVENT: one listener event's children span (at most) both child tables, so the two queries are run
    # unpaginated and the page is sliced from the combined result (a single event's children are few).
    album_results = await _query_listener_event_join(
        session=session,
        beets_library=beets_library,
        join_events_table=AlbumEvent,
        conditions=[col(AlbumEvent.listener_event_id) == entity_id],
    )
    track_results = await _query_listener_event_join(
        session=session,
        beets_library=beets_library,
        join_events_table=TrackEvent,
        conditions=[col(TrackEvent.listener_event_id) == entity_id],
    )
    return (album_results + track_results)[offset : offset + limit]
