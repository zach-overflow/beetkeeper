"""
The webhook stubs in this module are purely for documentation purposes only. See the docstring in
`beetkeeper.api.webhooks.__init__` for more details.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field


class SearchMissingSourcePathResult(BaseModel):
    """One search result. The key holding the path is whatever `downloader_hook.filepath_json_key` names."""

    model_config = ConfigDict(extra="allow")
    content_path: str | None = Field(
        default=None,
        description=(
            "Example path key (qBittorrent's name for it). beetkeeper reads the key named by the "
            "`downloader_hook.filepath_json_key` config and maps the value onto its `downloads_path`."
        ),
    )


# NOTE: since this is a webhook-only APIRouter, the `prefix` should not matter.
webhook_router = APIRouter()


@webhook_router.get("search-missing-source-path", response_model=list[SearchMissingSourcePathResult])
def search_missing_source_path(
    field: Annotated[
        str | None,
        Query(
            description=(
                "One query param per entry in the `downloader_hook.beet_field_to_dl_search_field` "
                "config: the param is named by the mapping's value and carries the library entry's beets field "
                "value (e.g. `album=Geogaddi&albumartist=Boards+of+Canada`)."
            )
        ),
    ] = None,
) -> Any:
    """
    Sent by beetkeeper to the configured downloader API (`downloader_hook.base_url` + `search_endpoint_path`)
    when a client requests `POST /api/import/find_missing_source_path` for a library entry whose
    source path was never recorded. The downloader answers with a JSON list of results (or one object);
    beetkeeper takes the first result's path. When `downloader_hook.api_key` is set, the request carries an
    `Authorization: Bearer <api_key>` header.
    """
