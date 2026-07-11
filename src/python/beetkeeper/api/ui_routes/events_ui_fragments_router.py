"""HTML fragment routes for the events page — recently ingested beets listener events from the DB."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from beetkeeper.api.api_routes.events_router import events
from beetkeeper.api.jinja_driver import get_templates
from beetkeeper.db.session import SessionDep

_LOGGER = logging.getLogger(__name__)
_RECENT_EVENT_LIMIT = 50
events_ui_fragments_router = APIRouter(prefix="/fragment/event")


@events_ui_fragments_router.get("", response_class=HTMLResponse)
async def event_fragment(request: Request, session: SessionDep) -> HTMLResponse:
    """Render an HTML fragment of the most recently ingested beets listener events (newest first).

    Delegates the event lookup to the JSON `GET /api/events` route coroutine, so the fragment and the
    public API always agree on the events payload.
    """
    events_response = await events(session=session, limit=_RECENT_EVENT_LIMIT)
    return get_templates().TemplateResponse(
        request=request,
        name="fragment_templates/event_fragment.html",
        context={"events": [record.model_dump() for record in events_response.events]},
    )
