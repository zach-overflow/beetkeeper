"""
HTMX fragment routes backing the `/search` page — the UI counterpart of the `/api/query/*` JSON routes.

Both call the same `core.BeetsLibrary` adapter; these return HTML partials for HTMX to swap in:
  * `GET /fragment/search/results` — run a beets list-style query, render the matching tracks/albums
    alongside each one's library location and the import source path(s) the beetkeeper plugin recorded.
  * `GET /fragment/search/stats`   — run a beets stats-style query over the same inputs (`beet stats`).
  * `GET /fragment/search/fields`  — render the available query fields reference (`beet fields`).
  * `GET /fragment/search/source-path` — ask the configured downloader client for an entry's unrecorded
    source folder (the `find_missing_source_path` API route's HTMX counterpart).

The `/search` page lets the user dispatch the same form inputs to either `results` (list) or `stats`.
"""

import logging
import shlex
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from beetkeeper.api.adapters import (
    find_missing_source_path,
    import_source_paths_by_album_id,
    import_source_paths_by_track_id,
    inferred_source_paths,
)
from beetkeeper.api.api_models import FindMissingSourcePathRequestParams, SearchResultsQueryParams
from beetkeeper.api.constants import LibrarySubject
from beetkeeper.api.dependencies import BeetsLibraryDep, DownloaderHookDep
from beetkeeper.api.jinja_driver import get_templates
from beetkeeper.db.session import SessionDep

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
    request: Request,
    library: BeetsLibraryDep,
    session: SessionDep,
    downloader: DownloaderHookDep,
    params: SearchResultsQueryParams,
) -> HTMLResponse:
    """
    `beet list`-style query: render one page of the matching tracks/albums as a table.

    Each row also shows the subject's current library path (its destination) and the import source path(s)
    recorded by the beetkeeper plugin's `import_task_files` push, looked up in the beetkeeper DB by beets
    id. Subjects with no recorded import fall back to an *inferred* source path (see `hooks_adapters`) —
    a track inherits its album's inference — and are otherwise flagged as unrecorded rather than shown blank.
    """
    parts = _build_query_parts(params.query, params.filepath, params.sort_by)
    error: str | None = None
    page_results: list[dict[str, Any]] = []
    total = 0
    source_paths_by_id: dict[int, list[str]] = {}
    inferred_by_id: dict[int, str] = {}
    try:
        query_method = library.query_albums if params.albums else library.query_items
        page_results, total = await query_method(parts, offset=params.offset, limit=params.page_size)
    except Exception as exc:  # surface invalid-query errors in the UI instead of a 500
        _LOGGER.debug(f"Search query failed: {exc}")
        error = str(exc)
    else:
        source_paths_lookup = import_source_paths_by_album_id if params.albums else import_source_paths_by_track_id
        source_paths_by_id = await source_paths_lookup(session, [row["id"] for row in page_results])
        inferred_by_id = await _inferred_source_paths_for_rows(session, page_results, albums=params.albums)

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
            "source_paths_by_id": source_paths_by_id,
            "inferred_by_id": inferred_by_id,
            "missing_source_count": sum(
                1 for row in page_results if row["id"] not in source_paths_by_id and row["id"] not in inferred_by_id
            ),
            "albums": params.albums,
            "error": error,
            "total": total,
            "page": params.page,
            "start_index": params.offset + 1,
            "end_index": params.offset + len(page_results),
            "base_params": base_params,
            "downloader_hook_enabled": downloader.enabled,
        },
    )


@search_ui_fragments_router.get("/source-path", response_class=HTMLResponse)
async def source_path_lookup_fragment(
    request: Request,
    library: BeetsLibraryDep,
    downloader: DownloaderHookDep,
    session: SessionDep,
    req_params: FindMissingSourcePathRequestParams,
) -> HTMLResponse:
    """Render the downloader's answer for an entry's source folder (persisted as an inference on a match)."""
    response = await find_missing_source_path(library, downloader, session, req_params)
    return get_templates().TemplateResponse(
        request=request, name="fragment_templates/source_path_lookup.html", context={"lookup": response}
    )


async def _inferred_source_paths_for_rows(
    session: SessionDep, rows: list[dict[str, Any]], *, albums: bool
) -> dict[int, str]:
    """Inferred source paths keyed by row id; a track row without its own falls back to its album's."""
    ids = [row["id"] for row in rows]
    if albums:
        return await inferred_source_paths(session, LibrarySubject.ALBUM, ids)
    by_track = await inferred_source_paths(session, LibrarySubject.TRACK, ids)
    album_ids = [row["album_id"] for row in rows if row["id"] not in by_track and row.get("album_id")]
    by_album = await inferred_source_paths(session, LibrarySubject.ALBUM, album_ids)
    for row in rows:
        if row["id"] not in by_track and row.get("album_id") in by_album:
            by_track[row["id"]] = by_album[row["album_id"]]
    return by_track


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
