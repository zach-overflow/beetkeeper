"""
Dedicated module exclusively for `fastapi.APIRouter`(s) which serve content via `TemplateResponse`s ( https://fastapi.tiangolo.com/advanced/templates/#using-jinja2templates ).
Any RESTful API endpoints should go outside of this module.

HTML Should be generated from HTML Jinja template(s) under
`src/python/beetkeeper/api/static/html_templates` (surfaced to our routers by `beetkeeper.api.constants.TEMPLATES`).
Templates may be added under that directory as needed, and all should extend from teh same common `src/python/beetkeeper/api/static/html_templates/base_template.html`.

Full pages live under `html_templates/page_templates/` and are served by `pages_ui_router`; HTMX
fragments live under `html_templates/fragment_templates/` and are served by `events_ui_fragments_router`.

Relevant documentation:
1. FastAPI HTML Templates: https://fastapi.tiangolo.com/advanced/templates/
2. HTMX: [docs](https://htmx.org/docs/) and [reference](https://htmx.org/reference/)

No Javascript should be used, other than HTMX (which is already vendored under `src/python/beetkeeper/api/static/js/htmx.min.js`).

Convention: every `TEMPLATES.TemplateResponse(...)` call MUST pass `request=request`. The shared
`base_template.html` resolves static asset URLs (CSS, vendored HTMX) via `url_for('static', ...)`, which
needs the request in the template context — omitting it raises at render time.
"""

from fastapi import APIRouter

from beetkeeper.api.ui_routes.auth_ui_router import auth_ui_router
from beetkeeper.api.ui_routes.events_ui_fragments_router import events_ui_fragments_router
from beetkeeper.api.ui_routes.import_ui_fragments_router import import_ui_fragments_router
from beetkeeper.api.ui_routes.pages_ui_router import pages_ui_router
from beetkeeper.api.ui_routes.search_ui_fragments_router import search_ui_fragments_router

# No prefix: pages are served at the site root (`/home`, `/events`, `/import`, `/search`) and fragments
# under `/fragment`. (`prefix="/"` is invalid — an APIRouter prefix must not end with `/`.)
ui_router = APIRouter(include_in_schema=False)
ui_router.include_router(auth_ui_router)
ui_router.include_router(pages_ui_router)
ui_router.include_router(events_ui_fragments_router)
ui_router.include_router(import_ui_fragments_router)
ui_router.include_router(search_ui_fragments_router)

__all__ = ["ui_router"]
