"""Bridges the import routes (JSON and HTMX) to the `ImportStore` and the read-only preview in `core.clean_slate`."""

from fastapi import HTTPException, status

from beetkeeper.api.api_models.import_api_models import CleanSlatePreviewRequest
from beetkeeper.core import BeetsLibrary, CleanSlatePreview, ImportJob, ImportStore
from beetkeeper.core.clean_slate import CleanSlateError
from beetkeeper.settings import UserConfig


async def require_import_job(store: ImportStore, job_id: str) -> ImportJob:
    """The job's current view, or a 404 when the store knows no job with that id."""
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No import job '{job_id}'.")
    return job


def reject_unsafe_clean_slate(plan: CleanSlatePreview, *, needs_confirmation_detail: str) -> None:
    """Refuse a clean slate its preview blocks: a 422 for blocking errors, else a 409 while the opt-in is missing."""
    if plan.errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" ".join(plan.errors))
    if plan.needs_confirmation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=needs_confirmation_detail)


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
