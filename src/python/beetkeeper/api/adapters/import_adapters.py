"""Bridges the clean-slate routes (JSON and HTMX) and the read-only preview in `core.clean_slate`."""

from fastapi import HTTPException, status

from beetkeeper.api.api_models.import_api_models import CleanSlatePreviewRequest
from beetkeeper.core import BeetsLibrary, CleanSlatePreview
from beetkeeper.core.clean_slate import CleanSlateError
from beetkeeper.settings import UserConfig


async def clean_slate_preview(
    library: BeetsLibrary, user_config: UserConfig, request: CleanSlatePreviewRequest
) -> CleanSlatePreview:
    """
    Run the read-only clean-slate preview for a route: an unknown entry is a 404, any other refusal a 422.

    The fields carried onto the fresh import are the keys of the `downloader_hook.beet_field_to_dl_search_field`
    setting, i.e. the fields the downloader hook searches by.
    """
    try:
        return await library.clean_slate_preview(
            request.clean_slate_target,
            request.source_path,
            downloads_path=user_config.downloads_path,
            allow_fewer_files=request.allow_fewer_files,
            preserve_fields=user_config.downloader_hook.beet_field_to_dl_search_field,
        )
    except CleanSlateError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.kind == "not_found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
