"""
Event endpoints which the `beetsplug.beetkeeper_plugin.event_listener.BeetKeeperClient` will push beets events to.

Each push is recorded as one `ListenerEvent` row plus its per-entity child rows (`AlbumEvent` / `TrackEvent`),
written through the async `SessionDep` dependency (see `beetkeeper.db.session`).
See also:
    https://beets.readthedocs.io/en/stable/dev/plugins/events.html
    `src/beetsplug/beetkeeper_plugin/event_listener.py`
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from beetkeeper.api.api_models import (
    AlbumEventBody,
    APIEventType,
    EventIngestResponse,
    EventsListResponse,
    ImportTaskFilesEventBody,
    ListenerEventRecord,
    MultiItemEventIngestResponse,
    TrackEventBody,
)
from beetkeeper.api.constants import RouteTag
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import SessionDep

_LOGGER = logging.getLogger(__name__)
# The push (POST) routes are for the beetkeeper plugin only, so each opts out of the public OpenAPI schema
# individually (a route-level `include_in_schema=True` cannot override a router-level `False`; FastAPI ANDs them).
events_router = APIRouter(prefix="/events", tags=[RouteTag.EVENT])


async def _record_listener_event(session: AsyncSession, event_type: APIEventType, pushed_at: datetime) -> int:
    """Inserts the parent `ListenerEvent` and flushes to obtain its generated `event_id` for child FKs."""
    listener_event = ListenerEvent(event_type=event_type, pushed_at=pushed_at)
    session.add(listener_event)
    await session.flush()  # populates the autoincrement `event_id` used as the child rows' FK
    return cast("int", listener_event.event_id)


@events_router.get("", status_code=status.HTTP_200_OK)
async def events(session: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> EventsListResponse:
    """
    Lists the most recently ingested beets listener events (newest first), each with the beets album/track
    ids of its child rows (the ones the beetkeeper event-listener plugin pushed to the POST endpoints).
    """
    recent_events = (
        (
            await session.execute(
                select(ListenerEvent)
                .order_by(col(ListenerEvent.pushed_at).desc(), col(ListenerEvent.event_id).desc())
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

    return EventsListResponse(
        events=[
            ListenerEventRecord(
                event_type=APIEventType(event.event_type),
                pushed_at=event.pushed_at,
                album_ids=album_ids_by_event.get(event.event_id, []),
                track_ids=track_ids_by_event.get(event.event_id, []),
            )
            for event in recent_events
        ]
    )


@events_router.post("/album", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def album(album_event: AlbumEventBody, session: SessionDep) -> EventIngestResponse:
    _LOGGER.debug(f"Processing album event type: {album_event.event_type} ...")
    listener_event_id = await _record_listener_event(session, album_event.event_type, album_event.pushed_at)
    session.add(AlbumEvent(listener_event_id=listener_event_id, beets_album_id=album_event.album_fields.id))
    await session.commit()
    return EventIngestResponse(event_type=album_event.event_type, ingested_id=album_event.album_fields.id)


@events_router.post("/track", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def track(track_event: TrackEventBody, session: SessionDep) -> EventIngestResponse:
    _LOGGER.debug(f"Processing track event type: {track_event.event_type} ...")
    listener_event_id = await _record_listener_event(session, track_event.event_type, track_event.pushed_at)
    session.add(
        TrackEvent(
            listener_event_id=listener_event_id,
            beets_item_id=track_event.track_fields.id,
            beets_album_id=track_event.track_fields.album_id,
        )
    )
    await session.commit()
    return EventIngestResponse(event_type=track_event.event_type, ingested_id=track_event.track_fields.id)


@events_router.post("/filesystem", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def filesystem(fs_event: ImportTaskFilesEventBody, session: SessionDep) -> MultiItemEventIngestResponse:
    _LOGGER.debug(f"Processing filesystem event type: {fs_event.event_type} ...")
    listener_event_id = await _record_listener_event(session, fs_event.event_type, fs_event.pushed_at)
    ingest_responses: list[EventIngestResponse] = []
    for item in fs_event.imported_items:
        session.add(
            TrackEvent(
                listener_event_id=listener_event_id,
                beets_item_id=item.track_fields.id,
                beets_album_id=item.track_fields.album_id,
            )
        )
        ingest_responses.append(EventIngestResponse(event_type=item.event_type, ingested_id=item.track_fields.id))
    await session.commit()
    return MultiItemEventIngestResponse(event_type=fs_event.event_type, event_ingest_responses=ingest_responses)
