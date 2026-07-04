"""Full-page HTML routes. Each renders a `page_templates/*.html` that extends `base_template.html`."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from beetkeeper.api.constants import TEMPLATES

pages_ui_router = APIRouter()


@pages_ui_router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request=request, name="page_templates/main_page.html", context={})


@pages_ui_router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request=request, name="page_templates/events_page.html", context={})


@pages_ui_router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request=request, name="page_templates/import_page.html", context={})


@pages_ui_router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request) -> HTMLResponse:
    """UI for the read-only `query_router` endpoints: search (list), library stats, and field reference.

    The page is static shell; its data loads via the `search_ui_fragments_router` HTMX fragments.
    """
    return TEMPLATES.TemplateResponse(request=request, name="page_templates/search_page.html", context={})
