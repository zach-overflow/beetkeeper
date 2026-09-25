"""
RESTful (JSON) endpoints to drive interactive beets imports.

Job state lives in the cross-process DB-backed `ImportStore`; the leader-elected `ImportWorker`
(`beetkeeper.core.import_worker`) runs the actual beets import. These routes only read/write the store, so
they work on any uvicorn process. HTML/HTMX equivalents live in `ui_routes.import_ui_fragments_router`.
"""

from fastapi import APIRouter, HTTPException, status

from beetkeeper.api.adapters import clean_slate_preview as _clean_slate_preview
from beetkeeper.api.adapters import find_missing_source_path as _lookup_source_path
from beetkeeper.api.api_models import (
    CleanSlatePreviewParams,
    CleanSlateSubmitRequest,
    FindMissingSourcePathRequest,
    FindMissingSourcePathResponse,
    ImportSubmitRequest,
    PageQueryParams,
)
from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import BeetsLibraryDep, DownloaderHookDep, ImportStoreDep, UserConfigDep
from beetkeeper.core import CleanSlatePreview, ImportDecision, ImportJob
from beetkeeper.db.session import SessionDep

import_router = APIRouter(prefix="/import", tags=[RouteTag.IMPORT])


@import_router.post("", status_code=status.HTTP_201_CREATED)
async def start_import(body: ImportSubmitRequest, store: ImportStoreDep) -> ImportJob:
    """Enqueue an import of the given paths and return the created (PENDING) job.

    Set `quiet=true` to import non-interactively (the `beet import -q` equivalent): no decision prompts.
    The optional per-job settings (`quiet`, `logpath`, `group_albums`, `flat`, `set_fields`) default to the
    corresponding beets config values when left unspecified.
    """
    return await store.create(
        body.paths,
        quiet=body.quiet,
        logpath=str(body.logpath) if body.logpath is not None else None,
        group_albums=body.group_albums,
        flat=body.flat,
        set_fields=body.set_fields,
    )


@import_router.get("/clean_slate/preview")
async def preview_clean_slate(
    params: CleanSlatePreviewParams, library: BeetsLibraryDep, user_config: UserConfigDep
) -> CleanSlatePreview:
    """Dry-run a clean-slate import without touching anything (see `POST /api/import/clean_slate`).

    Reports what the removal would delete (library files inside the beets directory, album art), what it
    would leave alone, the flexible attributes that would be lost and those re-applied to the fresh import
    (`fields_preserved`: the entry's values for the keys of the `downloader_hook.beet_field_to_dl_search_field`
    config), what the source folder holds, plus the blocking `errors`, non-blocking `warnings`, and whether the
    fewer-files opt-in is needed. 404 for an unknown beets id.
    """
    return await _clean_slate_preview(library, user_config, params)


@import_router.post("/clean_slate", status_code=status.HTTP_201_CREATED)
async def start_clean_slate(
    body: CleanSlateSubmitRequest, store: ImportStoreDep, library: BeetsLibraryDep, user_config: UserConfigDep
) -> ImportJob:
    """Enqueue a clean-slate import: remove the named library entry, then import its source folder afresh.

    The preview runs first: a blocking error is a 422, a source with fewer audio files than the entry has on
    disk is a 409 until `allow_fewer_files` is set, and an unknown beets id is a 404. The job is then
    tracked like any other import (poll it, answer its decisions, abort it via the routes below); the worker
    re-runs the preview as its guard right before removing anything.
    """
    plan = await _clean_slate_preview(library, user_config, body)
    if plan.errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" ".join(plan.errors))
    if plan.needs_confirmation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The source holds {plan.source_audio_files} audio file(s) but the entry has {plan.files_present} "
                "on disk; set allow_fewer_files=true to proceed anyway."
            ),
        )
    return await store.create(
        [body.source_path],
        quiet=body.quiet,
        logpath=str(body.logpath) if body.logpath is not None else None,
        set_fields=body.set_fields,
        clean_slate_album_id=body.beets_album_id,
        clean_slate_item_id=body.beets_item_id,
        clean_slate_allow_fewer_files=body.allow_fewer_files,
    )


@import_router.post("/find_missing_source_path")
async def find_missing_source_path(
    body: FindMissingSourcePathRequest,
    beets_library: BeetsLibraryDep,
    downloader_hook: DownloaderHookDep,
    session: SessionDep,
) -> FindMissingSourcePathResponse:
    """Ask the configured downloader client where a library album/track was originally downloaded to.

    Only useful for entries imported outside a beetkeeper context (so no source path was recorded): the
    recovered pre-import folder is what a clean-slate import of the entry needs. The entry's fields named in
    the beets config's `beetkeeper.downloader_hook.beet_field_to_dl_search_field` become the search
    request's query params (see the `search-missing-source-path` webhook). A match is stored as the entry's
    *inferred* source path (replacing any earlier inference), which the search page then shows labelled as
    inferred — separate from source paths recorded from the beetkeeper plugin's events. 409 when no
    downloader API is configured; 404 for an unknown beets id.
    """
    if not downloader_hook.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No downloader API is configured (see the `beetkeeper.downloader_hook` config section).",
        )
    response = await _lookup_source_path(beets_library, downloader_hook, session, body)
    if response is None:
        kind = "album" if body.is_album else "item"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No beets {kind} with id {body.beets_id}.")
    return response


@import_router.get("")
async def list_imports(store: ImportStoreDep, page: PageQueryParams) -> list[ImportJob]:
    """List one page of known import jobs, newest first (so page 1 shows the most recent submissions)."""
    jobs = await store.list()
    jobs.reverse()  # store.list() is oldest-first
    return page.slice(jobs)


@import_router.get("/{job_id}")
async def get_import(job_id: str, store: ImportStoreDep) -> ImportJob:
    """Return a single import job (poll this for status / the pending decision)."""
    return await _require_job(store, job_id)


@import_router.post("/{job_id}/decision")
async def decide_import(job_id: str, decision: ImportDecision, store: ImportStoreDep) -> ImportJob:
    """Answer the decision an import is parked on; 409 if it isn't awaiting one."""
    await _require_job(store, job_id)
    if not await store.submit_decision(job_id, decision):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job is not awaiting a decision.")
    return await _require_job(store, job_id)


@import_router.post("/{job_id}/abort")
async def abort_import(job_id: str, store: ImportStoreDep) -> ImportJob:
    """Request cooperative cancellation of an in-flight import."""
    await _require_job(store, job_id)
    await store.request_abort(job_id)
    return await _require_job(store, job_id)


async def _require_job(store: ImportStoreDep, job_id: str) -> ImportJob:
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No import job '{job_id}'.")
    return job
