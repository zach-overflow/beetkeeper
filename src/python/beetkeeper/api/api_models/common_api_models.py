"""
General purpose Pydantic models for FastAPI route handlers, such as models wrapping
common pagination query parameters, or common filtering query parameters.

FastAPI resolves a query-param model only when it is the route's sole (non-dependency) parameter —
mixing one with individually declared query params degrades it to a scalar param. Routes needing
params beyond pagination therefore get a single model subclassing `PageQueryParamsModel`.

See also:
    https://fastapi.tiangolo.com/tutorial/path-params/
    https://fastapi.tiangolo.com/tutorial/query-param-models/
    https://fastapi.tiangolo.com/tutorial/dependencies/classes-as-dependencies/#type-annotation-vs-depends
"""

from collections.abc import Sequence
from enum import IntEnum
from pathlib import Path
from typing import Annotated, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field


class PageSize(IntEnum):
    """Constants for pagination and query limit sizes."""

    MAX_PAGE_SIZE = 100
    DEFAULT_PAGE_SIZE = 25
    EVENT_UI_PAGE_SIZE = 50


_T = TypeVar("_T")


class PageQueryParamsModel(BaseModel):
    """
    Common pagination query parameters with standardized limits.

    Should be used as in FastAPI route handler signatures with a `Annotated[PageQueryParams, Query()]` type hint.
    """

    page: int = Field(default=1, ge=1, description="The page number, 1-indexed.")
    page_size: int = Field(
        default=PageSize.DEFAULT_PAGE_SIZE, ge=1, le=PageSize.MAX_PAGE_SIZE, description="Maximum results per page."
    )

    @property
    def offset(self) -> int:
        """Number of results to offset by, based on `page` and `page_size`."""
        return (self.page - 1) * self.page_size

    def slice(self, items: Sequence[_T]) -> list[_T]:
        """Return this page's slice of an already-materialized result sequence."""
        return list(items[self.offset : self.offset + self.page_size])


class ListQueryParamsModel(PageQueryParamsModel):
    """Query params for `GET /api/query/list` (pagination plus the beets `list` query inputs).

    For each query param and its corresponding beets query search filter, see:
        https://beets.readthedocs.io/en/v2.12.0/reference/query.html#combining-keywords
    """

    albums: bool = Field(default=False, description="Like `-a`; return albums instead of individual tracks.")
    keyword: list[str] | None = Field(
        default=None, description="Repeatable bare-keyword query parts (substring match across default fields)."
    )
    field: list[str] | None = Field(
        default=None,
        description="Repeatable `field:value` parts (exact `=`, regex `::`, numeric/date ranges all supported).",
    )
    phrase: str | None = Field(default=None, description="A single multi-word phrase part.")
    filepath: Path | None = Field(default=None, description="A path within the beets library (becomes a path query).")
    sort_by: str | None = Field(default=None, description="A beets sort token, e.g. `year+` or `artist-`.")

    def query_parts(self) -> list[str]:
        """Assemble the beets query parts from the individual query params, in CLI argument order."""
        parts: list[str] = []
        if self.keyword:
            parts.extend(self.keyword)
        if self.field:
            parts.extend(self.field)
        if self.phrase:
            parts.append(self.phrase)
        if self.filepath:
            parts.append(str(self.filepath))
        if self.sort_by:
            parts.append(self.sort_by)
        return parts


class SearchResultsQueryParamsModel(PageQueryParamsModel):
    """Query params for the `GET /fragment/search/results` HTMX fragment route."""

    query: str = Field(default="", description="Free-text beets query, split like the beets CLI.")
    albums: bool = Field(default=False, description="Return albums instead of individual tracks.")
    filepath: str | None = Field(default=None, description="A path within the beets library.")
    sort_by: str | None = Field(default=None, description="A beets sort token, e.g. `year+` or `artist-`.")


# A `type` (PEP 695) alias is lazy, which hides the `Query()` metadata from FastAPI's signature
# inspection — the model would then be treated as a request body param. Keep these plain aliases.
PageQueryParams = Annotated[PageQueryParamsModel, Query()]
ListQueryParams = Annotated[ListQueryParamsModel, Query()]
SearchResultsQueryParams = Annotated[SearchResultsQueryParamsModel, Query()]
