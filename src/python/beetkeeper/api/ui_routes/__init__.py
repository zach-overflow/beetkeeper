"""
Dedicated module exclusively for `fastapi.APIRouter`(s) which serve content via `TemplateResponse`s ( https://fastapi.tiangolo.com/advanced/templates/#using-jinja2templates ).
Any RESTful API endpoints should go outside of this module.

HTML Should be generated from HTML Jinja template(s) under
`src/python/beetkeeper/api/static/html_templates` (surfaced to our routers by `beetkeeper.api.constants.TEMPLATES`).
Templates may be added under that directory as needed, and all should extend from teh same common `src/python/beetkeeper/api/static/html_templates/base_template.html`.

See `src/python/beetkeeper/api/static/html_templates/example_templates/example_full_page.html` for an example of
how HTML templates are expected to consistently render the HTML body inside a content block.

Relevant documentation:
1. FastAPI HTML Templates: https://fastapi.tiangolo.com/advanced/templates/
2. HTMX: [docs](https://htmx.org/docs/) and [reference](https://htmx.org/reference/)

No Javascript should be used, other than HTMX (which is already vendored under `src/python/beetkeeper/api/static/js/htmx.min.js`).

Convention: every `TEMPLATES.TemplateResponse(...)` call MUST pass `request=request`. The shared
`base_template.html` resolves static asset URLs (CSS, vendored HTMX) via `url_for('static', ...)`, which
needs the request in the template context — omitting it raises at render time.

TODO[Claude]: the docstring example reference was stale (pointed at the deleted
    `query_templates/search_form.html`); confirm `example_templates/example_full_page.html` is the
    intended canonical example, and either implement or delete the now-empty `search_page.py` sibling.
TODO[Claude]: this `ui_router` is defined but never mounted — `beetkeeper.api.fastapi_app` only includes
    `api_router`. Include `ui_router` there (it is intentionally NOT under the `/api` prefix).
"""

from fastapi import APIRouter

# TODO[Claude]: broken import — the source root is `src/python`, so the package path is
#     `beetkeeper.api.ui_routes...`, NOT `python.beetkeeper...`. This import will raise ModuleNotFoundError.
from python.beetkeeper.api.ui_routes.example_ui_router import example_ui_router

ui_router = APIRouter(prefix="/ui")
ui_router.include_router(example_ui_router)

__all__ = ["ui_router"]
