"""HTML fragment routes for the events page — recently ingested beets listener events from the DB."""

import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlmodel import col

from beetkeeper.api.jinja_driver import get_templates
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import SessionDep

_LOGGER = logging.getLogger(__name__)
_RECENT_EVENT_LIMIT = 50
events_ui_fragments_router = APIRouter(prefix="/fragment/event")


@events_ui_fragments_router.get("", response_class=HTMLResponse)
async def event_fragment(request: Request, session: SessionDep) -> HTMLResponse:
    """Render an HTML fragment of the most recently ingested beets listener events (newest first).

    Each event is the parent `ListenerEvent` plus the beets album/track ids of its child rows (the ones the
    beetkeeper event-listener plugin posted to `/api/events`).
    """
    recent_events = (
        (
            await session.execute(
                select(ListenerEvent)
                .order_by(col(ListenerEvent.pushed_at).desc(), col(ListenerEvent.event_id).desc())
                .limit(_RECENT_EVENT_LIMIT)
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

    events: list[dict[str, Any]] = [
        {
            "event_type": event.event_type,
            "pushed_at": event.pushed_at,
            "album_ids": album_ids_by_event.get(event.event_id, []),
            "track_ids": track_ids_by_event.get(event.event_id, []),
        }
        for event in recent_events
    ]
    return get_templates().TemplateResponse(
        request=request, name="fragment_templates/event_fragment.html", context={"events": events}
    )
