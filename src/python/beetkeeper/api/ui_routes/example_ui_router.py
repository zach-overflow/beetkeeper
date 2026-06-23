import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from beetkeeper.api.constants import TEMPLATES

_LOGGER = logging.getLogger(__name__)
# TODO[Claude]: misleading prefix — a UI router using `/config` collides conceptually with the RESTful
#     `config_router` and yields the odd path `/ui/config/example-1`. Pick a domain-meaningful prefix.
example_ui_router = APIRouter(prefix="/config")


# TODO[Claude]: missing return type hint (`-> HTMLResponse`); type hints are required per CLAUDE.md.
@example_ui_router.get("/example-1", response_class=HTMLResponse)
async def example_full_html_page(request: Request):
    """Example route which returns an HTML block, rendered as a full page, with a single jinja template variable."""
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y, %H:%M:%S")
    _LOGGER.debug(f"Accessed page at {date_str=}")
    # TODO[Claude]: template `name` is wrong relative to the loader root. `TEMPLATES` is rooted at
    #     `static/html_templates` (see `beetkeeper.api.constants`), so the name must be
    #     `example_templates/example_full_page.html` — the `static/html_templates/` prefix here will
    #     cause a TemplateNotFound.
    return TEMPLATES.TemplateResponse(
        request=request,
        name="static/html_templates/example_templates/example_full_page.html",
        context={"access_time_utc": date_str},
    )


# TODO: implement these 2 examples
# TODO[Claude]: these HTMX examples return partial HTML (a table, then a row). Decide the fragment-rendering
#     mechanism first: plain `Jinja2Templates` renders whole templates, whereas returning a single block for
#     an HTMX swap is what the declared `jinja2-fragments` dependency (`Jinja2Blocks`) provides. See the
#     related TODO in `beetkeeper.api.constants`.
# @example_ui_router.get("/example-2", response_class=HTMLResponse)
# async def render_table(request: Request):
#     """
#     Example route which returns an HTML table, composed of HTMX elements which render UI components from
#     their own subsequent HTTP requests.
#     """
#     return TEMPLATES.TemplateResponse(
#         request=request,
#         name="static/html_templates/example_templates/example_full_page.html",
#         context={"access_time_utc": date_str},
#     )


# async def render_table_row(request: Request):
#     """
#     Example route which returns an HTML table row, with templated values computed arbitrarily.
#     """
#     return TEMPLATES.TemplateResponse(
#         request=request,
#         name="static/html_templates/example_templates/example_full_page.html",
#         context={"access_time_utc": date_str},
#     )
