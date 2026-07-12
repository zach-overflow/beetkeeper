"""Full-page HTML routes. Each renders a `page_templates/*.html` that extends `base_template.html`."""

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from beetkeeper.api.api_models.import_api_models import (
    import_config_flag,
    import_config_logpath,
    import_config_set_fields,
)
from beetkeeper.api.jinja_driver import get_templates

pages_ui_router = APIRouter()


@pages_ui_router.get("/")
async def default_page() -> RedirectResponse:
    return RedirectResponse(url="/search", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@pages_ui_router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request) -> HTMLResponse:
    return get_templates().TemplateResponse(request=request, name="page_templates/main_page.html", context={})


@pages_ui_router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request) -> HTMLResponse:
    return get_templates().TemplateResponse(request=request, name="page_templates/events_page.html", context={})


@pages_ui_router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request) -> HTMLResponse:
    """The import page. The form's option controls are prefilled from the beets config's `import` section,
    so submitting the untouched form matches a plain `beet import` (and any change is an explicit override).
    """
    logpath = import_config_logpath()
    import_defaults = {
        "quiet": import_config_flag("quiet"),
        "group_albums": import_config_flag("group_albums"),
        "flat": import_config_flag("flat"),
        "logpath": str(logpath) if logpath is not None else "",
        "set_fields": "\n".join(f"{key}={value}" for key, value in import_config_set_fields().items()),
    }
    context = {"import_defaults": import_defaults}
    return get_templates().TemplateResponse(request=request, name="page_templates/import_page.html", context=context)


@pages_ui_router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request) -> HTMLResponse:
    """UI for the read-only `query_router` endpoints: search (list), library stats, and field reference.

    The page is static shell; its data loads via the `search_ui_fragments_router` HTMX fragments.
    """
    return get_templates().TemplateResponse(request=request, name="page_templates/search_page.html", context={})
