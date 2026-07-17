from collections.abc import Iterable
from enum import StrEnum, unique
from pathlib import Path
from textwrap import dedent
from typing import Final, Required, TypedDict

STATIC_DIRPATH: Final[Path] = Path(__file__).resolve().parent / "static"


@unique
class RouteTag(StrEnum):
    """Collection of all possible tag names we add to the `APIRouter` instances."""

    AUTH = "authentication"
    EVENT = "events"
    MONITOR = "monitoring"
    IMPORT = "imports"
    QUERY = "query"


class _OpenApiTagMetadata(TypedDict):
    """See https://fastapi.tiangolo.com/tutorial/metadata/#create-metadata-for-tags"""

    name: Required[RouteTag]
    description: Required[str]


OPENAPI_TAG_METADATA: Final[Iterable[_OpenApiTagMetadata]] = (
    {
        "name": RouteTag.AUTH,
        "description": dedent(
            """\
            Used only when optional "beetkeeper.auth.enable_login_protection" is "true". 
            Routes for simple login / logout flows. Beetkeeper does not support multiple user identities.
            Only handles authentication, with implicit authorization to everything for an authenticated client.
            """
        ),
    },
    {
        "name": RouteTag.IMPORT,
        "description": dedent(
            """\
            Routes for managing [beets imports](https://beets.readthedocs.io/en/stable/reference/cli.html#import).
            Offer API-based import execution, import history, import choice selection, and more.
            For automated beets setups, you will typically rely on these endpoints the most. 
            These endpoints also power the frontend import management web UI page.
            """
        ),
    },
    {
        "name": RouteTag.QUERY,
        "description": dedent(
            """\
            Routes for [querying your beets library](https://beets.readthedocs.io/en/stable/reference/query.html).
            Supports API-based queries, using standard `beets` query syntax. Useful for checking the status of your
            beets-managed library. These endpoints also power the frontend query UI page.
            """
        ),
    },
    {
        "name": RouteTag.EVENT,
        "description": dedent(
            """\
            Routes pertaining to [beets events](https://beets.readthedocs.io/en/stable/dev/plugins/events.html).
            Documented routes read-only. The [beetkeeper-plugin library](https://pypi.org/project/beetkeeper-plugin/)
            automatically pushes beets events to the beetkeeper server. Events serve to provide a full historical
            trace of any / all beets imports, file operations, etc. Helpful for tracing origins, or fine-tuning beets
            configurations, especially in automated setups.
            """
        ),
    },
    {"name": RouteTag.MONITOR, "description": "Routes for beetkeeper system observability, and availability checks."},
)
