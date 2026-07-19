"""Read-only beets query routes (`list`, `stats`, `fields`), backed by `core.BeetsLibrary`."""

import logging
from typing import Any

from fastapi import APIRouter

from beetkeeper.api.api_models import ListQueryParams
from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import BeetsLibraryDep

_LOGGER = logging.getLogger(__name__)
query_router = APIRouter(prefix="/query", tags=[RouteTag.QUERY])


@query_router.get("/list")
async def list_(  # trailing underscore: avoid shadowing the builtin `list` (used in the return annotation).
    library: BeetsLibraryDep, params: ListQueryParams
) -> list[dict[str, Any]]:
    """Execute `beet list ...`: return one page of matching tracks (or albums) as JSON objects.

    The query params (pagination plus the beets query inputs, some repeatable) are documented on
    `ListQueryParamsModel`.

    See: https://beets.readthedocs.io/en/v2.12.0/reference/cli.html#list
    """
    query_method = library.query_albums if params.albums else library.query_items
    results, _total = await query_method(params.query_parts(), offset=params.offset, limit=params.page_size)
    return results


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
