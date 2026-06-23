"""
Event endpoints which the `beetsplug.beetkeeper_plugin.event_listener.BeetKeeperClient` will push beets events to.
See also:
    https://beets.readthedocs.io/en/stable/dev/plugins/events.html
    `src/beetsplug/beetkeeper_plugin/event_listener.py`
"""

import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from beetkeeper.api.api_models import (
    AlbumEventBody,
    EventIngestResponse,
    ImportTaskFilesEventBody,
    MultiItemEventIngestResponse,
    TrackEventBody,
)

_LOGGER = logging.getLogger(__name__)
events_router = APIRouter(prefix="/events")


@events_router.post("/album", status_code=status.HTTP_201_CREATED)
async def album(album_event: AlbumEventBody) -> EventIngestResponse:
    _LOGGER.debug(f"Processing album event type: {str(album_event.event_type)} ...")
    return EventIngestResponse(event_type=album_event.event_type, ingested_id=album_event.album_fields.id)


@events_router.post("/track", status_code=status.HTTP_201_CREATED)
async def track(track_event: TrackEventBody) -> EventIngestResponse:
    _LOGGER.debug(f"Processing track event type: {str(track_event.event_type)} ...")
    return JSONResponse(content={}, status_code=200)


@events_router.post("/filesystem", status_code=status.HTTP_201_CREATED)
async def filesystem(fs_event: ImportTaskFilesEventBody) -> MultiItemEventIngestResponse:
    _LOGGER.debug(f"Processing album event type: {str(fs_event.event_type)} ...")
    return JSONResponse(content={}, status_code=200)
