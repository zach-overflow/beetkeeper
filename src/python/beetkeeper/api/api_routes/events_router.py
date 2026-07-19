"""
Event endpoints which the beets plugin's `beetsplug.beetkeeper_plugin.beetkeeper_plugin._BeetKeeperClient`
pushes beets events to.

Each push is recorded as one `ListenerEvent` row plus its per-entity child rows (`AlbumEvent` / `TrackEvent`),
written through the async `SessionDep` dependency (see `beetkeeper.db.session`).
See also:
    https://beets.readthedocs.io/en/stable/dev/plugins/events.html
    `src/beetsplug/beetkeeper_plugin/beetkeeper_plugin.py`
"""

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from beetkeeper.api.adapters import listener_event_lookup_by_type_and_id, listener_event_records_lookup
from beetkeeper.api.api_models import (
    AlbumEventBody,
    EventIngestResponse,
    EventSearchResponse,
    EventsListResponse,
    ImportTaskFilesEventBody,
    MultiItemEventIngestResponse,
    PageQueryParams,
    TrackEventBody,
)
from beetkeeper.api.constants import EventLookupEntityType, RouteTag
from beetkeeper.api.dependencies import BeetsLibraryDep
from beetkeeper.constants import BeetsEventType
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import SessionDep

# TODO[https://github.com/zach-overflow/beetkeeper/issues/75]: replace these log calls with non-blocking calls
# _LOGGER = logging.getLogger(__name__)
# The push (POST) routes are for the beetkeeper plugin only, so each opts out of the public OpenAPI schema
# individually (a route-level `include_in_schema=True` cannot override a router-level `False`; FastAPI ANDs them).
events_router = APIRouter(prefix="/events", tags=[RouteTag.EVENT])


async def _record_listener_event(session: AsyncSession, event_type: BeetsEventType, pushed_at: datetime) -> int:
    """Inserts the parent `ListenerEvent` and flushes to obtain its generated `event_id` for child FKs."""
    # _LOGGER.debug(f"Processing track event type: {event_type} ...")
    listener_event = ListenerEvent(event_type=event_type, pushed_at=pushed_at)
    session.add(listener_event)
    await session.flush()  # populates the autoincrement `event_id` used as the child rows' FK
    # _LOGGER.debug(f"Write beets event to db took {perf_counter() - start} seconds.")
    return cast("int", listener_event.event_id)


@events_router.get("", status_code=status.HTTP_200_OK)
async def events(session: SessionDep, page_query_params: PageQueryParams) -> EventsListResponse:
    """
    Lists the requested page of ingested beets listener events (newest first), each with the beets album/track
    ids of its child rows (the ones the beetkeeper event-listener plugin pushed to the POST endpoints).
    """
    event_records_list = await listener_event_records_lookup(
        session=session, offset=page_query_params.offset, limit=page_query_params.page_size
    )
    return EventsListResponse(events=event_records_list)


@events_router.get("/album/{beets_album_id}", status_code=status.HTTP_200_OK)
async def by_album_id(
    beets_album_id: Annotated[int, Path(title="beets album ID to search listener events by", gt=-1)],
    session: SessionDep,
    library: BeetsLibraryDep,
    page_query_params: PageQueryParams,
) -> EventSearchResponse:
    """Returns the list of results for events associated with the beets album ID, if any exist."""
    search_results = await listener_event_lookup_by_type_and_id(
        entity_type=EventLookupEntityType.ALBUM,
        entity_id=beets_album_id,
        session=session,
        offset=page_query_params.offset,
        limit=page_query_params.page_size,
        beets_library=library,
    )
    return EventSearchResponse(results=search_results)


@events_router.get("/track/{beets_track_id}", status_code=status.HTTP_200_OK)
async def by_track_id(
    beets_track_id: Annotated[int, Path(title="beets track ID to search listener events by", gt=-1)],
    session: SessionDep,
    library: BeetsLibraryDep,
    page_query_params: PageQueryParams,
) -> EventSearchResponse:
    """Returns the list of results for events associated with the beets item ID, if any exist."""
    search_results = await listener_event_lookup_by_type_and_id(
        entity_type=EventLookupEntityType.TRACK,
        entity_id=beets_track_id,
        session=session,
        offset=page_query_params.offset,
        limit=page_query_params.page_size,
        beets_library=library,
    )
    return EventSearchResponse(results=search_results)


@events_router.get("/{beetkeeper_event_id}", status_code=status.HTTP_200_OK)
async def by_event_id(
    beetkeeper_event_id: Annotated[int, Path(title="beetkeeper event ID to search listener events by", gt=-1)],
    session: SessionDep,
    library: BeetsLibraryDep,
    page_query_params: PageQueryParams,
) -> EventSearchResponse:
    """Returns the list of results for events associated with the beetkeeper event item ID, if any exist."""
    search_results = await listener_event_lookup_by_type_and_id(
        entity_type=EventLookupEntityType.BKEVENT,
        entity_id=beetkeeper_event_id,
        session=session,
        offset=page_query_params.offset,
        limit=page_query_params.page_size,
        beets_library=library,
    )
    return EventSearchResponse(results=search_results)


@events_router.post("/album", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def album(album_event: AlbumEventBody, session: SessionDep) -> EventIngestResponse:
    listener_event_id = await _record_listener_event(session, album_event.event_type, album_event.pushed_at)
    session.add(AlbumEvent(listener_event_id=listener_event_id, beets_album_id=album_event.album_fields.id))
    await session.commit()
    return EventIngestResponse(event_type=album_event.event_type, ingested_id=album_event.album_fields.id)


@events_router.post("/track", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def track(track_event: TrackEventBody, session: SessionDep) -> EventIngestResponse:
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
