"""
Event endpoints which the `beetsplug.beetkeeper_plugin.event_listener.BeetKeeperClient` will push beets events to.

Each push is recorded as one `ListenerEvent` row plus its per-entity child rows (`AlbumEvent` / `TrackEvent`),
written through the async `SessionDep` dependency (see `beetkeeper.db.session`).
See also:
    https://beets.readthedocs.io/en/stable/dev/plugins/events.html
    `src/beetsplug/beetkeeper_plugin/event_listener.py`
"""

import logging
from datetime import datetime
from typing import cast

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from beetkeeper.api.api_models import (
    AlbumEventBody,
    APIEventType,
    EventIngestResponse,
    ImportTaskFilesEventBody,
    MultiItemEventIngestResponse,
    TrackEventBody,
)
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import SessionDep

_LOGGER = logging.getLogger(__name__)
events_router = APIRouter(prefix="/events")


async def _record_listener_event(session: AsyncSession, event_type: APIEventType, pushed_at: datetime) -> int:
    """Inserts the parent `ListenerEvent` and flushes to obtain its generated `event_id` for child FKs."""
    listener_event = ListenerEvent(event_type=event_type, pushed_at=pushed_at)
    session.add(listener_event)
    await session.flush()  # populates the autoincrement `event_id` used as the child rows' FK
    return cast("int", listener_event.event_id)


@events_router.post("/album", status_code=status.HTTP_201_CREATED)
async def album(album_event: AlbumEventBody, session: SessionDep) -> EventIngestResponse:
    _LOGGER.debug("Processing album event type: %s ...", album_event.event_type)
    listener_event_id = await _record_listener_event(session, album_event.event_type, album_event.pushed_at)
    session.add(AlbumEvent(listener_event_id=listener_event_id, beets_album_id=album_event.album_fields.id))
    await session.commit()
    return EventIngestResponse(event_type=album_event.event_type, ingested_id=album_event.album_fields.id)


@events_router.post("/track", status_code=status.HTTP_201_CREATED)
async def track(track_event: TrackEventBody, session: SessionDep) -> EventIngestResponse:
    _LOGGER.debug("Processing track event type: %s ...", track_event.event_type)
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


@events_router.post("/filesystem", status_code=status.HTTP_201_CREATED)
async def filesystem(fs_event: ImportTaskFilesEventBody, session: SessionDep) -> MultiItemEventIngestResponse:
    _LOGGER.debug("Processing filesystem event type: %s ...", fs_event.event_type)
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
