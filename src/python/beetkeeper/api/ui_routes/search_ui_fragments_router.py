"""
HTMX fragment routes backing the `/search` page — the UI counterpart of the `/api/query/*` JSON routes.

Both call the same `core.BeetsLibrary` adapter; these return HTML partials for HTMX to swap in:
  * `GET /fragment/search/results` — run a beets list-style query, render the matching tracks/albums.
  * `GET /fragment/search/stats`   — run a beets stats-style query over the same inputs (`beet stats`).
  * `GET /fragment/search/fields`  — render the available query fields reference (`beet fields`).

The `/search` page lets the user dispatch the same form inputs to either `results` (list) or `stats`.
"""

import logging
import shlex
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from beetkeeper.api.api_models import SearchResultsQueryParams
from beetkeeper.api.dependencies import BeetsLibraryDep
from beetkeeper.api.jinja_driver import get_templates

_LOGGER = logging.getLogger(__name__)
search_ui_fragments_router = APIRouter(prefix="/fragment/search")


def _build_query_parts(query: str, filepath: str | None, sort_by: str | None = None) -> list[str]:
    """Split a free-text beets query into parts, then append optional path-filter and sort tokens."""
    try:
        parts = shlex.split(query)  # split like the beets CLI (honours quoted phrases)
    except ValueError:
        parts = query.split()
    if filepath:
        parts.append(filepath)  # a path-like part becomes an explicit `path:` query (see parse_query_parts)
    if sort_by:
        parts.append(sort_by)
    return parts


@search_ui_fragments_router.get("/results", response_class=HTMLResponse)
async def search_results_fragment(
    request: Request, library: BeetsLibraryDep, params: SearchResultsQueryParams
) -> HTMLResponse:
    """`beet list`-style query: render one page of the matching tracks/albums as a table."""
    parts = _build_query_parts(params.query, params.filepath, params.sort_by)
    error: str | None = None
    page_results: list[dict[str, Any]] = []
    total = 0
    try:
        query_method = library.query_albums if params.albums else library.query_items
        page_results, total = await query_method(parts, offset=params.offset, limit=params.page_size)
    except Exception as exc:  # surface invalid-query errors in the UI instead of a 500
        _LOGGER.debug(f"Search query failed: {exc}")
        error = str(exc)

    base_params = urlencode(
        {
            "query": params.query,
            "albums": "true" if params.albums else "false",
            "filepath": params.filepath or "",
            "sort_by": params.sort_by or "",
            "page_size": params.page_size,
        }
    )
    return get_templates().TemplateResponse(
        request=request,
        name="fragment_templates/search_results.html",
        context={
            "results": page_results,
            "albums": params.albums,
            "error": error,
            "total": total,
            "page": params.page,
            "start_index": params.offset + 1,
            "end_index": params.offset + len(page_results),
            "base_params": base_params,
        },
    )


@search_ui_fragments_router.get("/stats", response_class=HTMLResponse)
async def search_stats_fragment(
    request: Request, library: BeetsLibraryDep, query: str = "", filepath: str | None = None
) -> HTMLResponse:
    """`beet stats`-style query: render the stats summary for the matching items (whole library if empty)."""
    parts = _build_query_parts(query, filepath)
    error: str | None = None
    stats: dict[str, Any] | None = None
    try:
        stats = await library.stats(parts)
    except Exception as exc:  # surface invalid-query errors in the UI instead of a 500
        _LOGGER.debug(f"Stats query failed: {exc}")
        error = str(exc)

    return get_templates().TemplateResponse(
        request=request, name="fragment_templates/search_stats.html", context={"stats": stats, "error": error}
    )


@search_ui_fragments_router.get("/fields", response_class=HTMLResponse)
async def search_fields_fragment(request: Request, library: BeetsLibraryDep) -> HTMLResponse:
    """Render the available query fields reference fragment."""
    return get_templates().TemplateResponse(
        request=request, name="fragment_templates/search_fields.html", context={"fields": await library.fields()}
    )
