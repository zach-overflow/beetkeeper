"""Read-only beets query routes (`list`, `stats`, `fields`), backed by `core.BeetsLibrary`."""

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query

from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import BeetsLibraryDep, PageParamsDep

_LOGGER = logging.getLogger(__name__)
query_router = APIRouter(prefix="/query", tags=[RouteTag.QUERY])


# For each possible query param and its corresponding beets query search filter, see:
# https://beets.readthedocs.io/en/v2.12.0/reference/query.html#combining-keywords
# Some params are repeatable (multiple values per request) via the FastAPI `Query()` list pattern:
# https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#query-parameter-list-multiple-values
@query_router.get("/list")
async def list_(  # trailing underscore: avoid shadowing the builtin `list` (used in annotations below).
    library: BeetsLibraryDep,
    page: PageParamsDep,
    albums: bool = False,
    keyword: Annotated[list[str] | None, Query()] = None,
    field: Annotated[list[str] | None, Query()] = None,
    phrase: str | None = None,
    filepath: Path | None = None,
    sort_by: str | None = None,
) -> list[dict[str, Any]]:
    """Execute `beet list ...`: return one page of matching tracks (or albums) as JSON objects.

    Args:
        library: injected beets library adapter.
        page: pagination query params (`page`, `page_size`).
        albums: like `-a`; return albums instead of individual tracks.
        keyword: repeatable bare-keyword query parts (substring match across default fields).
        field: repeatable `field:value` parts (exact `=`, regex `::`, numeric/date ranges all supported).
        phrase: a single multi-word phrase part.
        filepath: a path within the beets library (becomes a path query).
        sort_by: a beets sort token, e.g. `year+` or `artist-`.

    See: https://beets.readthedocs.io/en/v2.12.0/reference/cli.html#list
    """
    query_parts: list[str] = []
    if keyword:
        query_parts.extend(keyword)
    if field:
        query_parts.extend(field)
    if phrase:
        query_parts.append(phrase)
    if filepath:
        query_parts.append(str(filepath))
    if sort_by:
        query_parts.append(sort_by)
    results = await (library.query_albums(query_parts) if albums else library.query_items(query_parts))
    return page.slice(results)


@query_router.get("/stats")
async def stats(library: BeetsLibraryDep) -> dict[str, Any]:
    """Execute `beet stats`: track count, total time, approximate size, and artist/album counts.

    See: https://beets.readthedocs.io/en/v2.12.0/reference/cli.html#stats
    """
    return await library.stats()


@query_router.get("/fields")
async def fields(library: BeetsLibraryDep) -> dict[str, list[str]]:
    """Execute `beet fields`: the item/album query fields and flexible attributes available.

    See: https://beets.readthedocs.io/en/v2.12.0/reference/cli.html#fields
    """
    return await library.fields()
