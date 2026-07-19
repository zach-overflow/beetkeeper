"""HTML fragment routes for the events page — recently ingested beets listener events from the DB."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from beetkeeper.api.adapters import listener_event_records_lookup
from beetkeeper.api.api_models import PageSize
from beetkeeper.api.jinja_driver import get_templates
from beetkeeper.db.session import SessionDep

events_ui_fragments_router = APIRouter(prefix="/fragment/event")


@events_ui_fragments_router.get("", response_class=HTMLResponse)
async def recent_events_fragment(request: Request, session: SessionDep) -> HTMLResponse:
    """
    Render an HTML fragment of the most recently ingested beets listener events (newest first).

    Delegates the event lookup to the same adapter as the JSON `GET /api/events` route, so the fragment
    and the public API always agree on the events payload.
    """
    event_records_list = await listener_event_records_lookup(
        session=session, offset=0, limit=PageSize.EVENT_UI_PAGE_SIZE
    )
    return get_templates().TemplateResponse(
        request=request,
        name="fragment_templates/event_fragment.html",
        context={"events": [record.model_dump() for record in event_records_list]},
    )
