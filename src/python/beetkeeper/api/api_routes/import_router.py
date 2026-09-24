"""
RESTful (JSON) endpoints to drive interactive beets imports.

Job state lives in the cross-process DB-backed `ImportStore`; the leader-elected `ImportWorker`
(`beetkeeper.core.import_worker`) runs the actual beets import. These routes only read/write the store, so
they work on any uvicorn process. HTML/HTMX equivalents live in `ui_routes.import_ui_fragments_router`.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from beetkeeper.api.adapters import find_missing_source_path as _lookup_source_path
from beetkeeper.api.api_models import (
    FindMissingSourcePathRequestParams,
    FindMissingSourcePathResponse,
    ImportSubmitRequest,
    PageQueryParams,
    ReimportSubmitRequest,
)
from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import BeetsLibraryDep, DownloaderHookDep, ImportStoreDep
from beetkeeper.core import ImportDecision, ImportJob
from beetkeeper.db.session import SessionDep

_LOGGER = logging.getLogger(__name__)
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


@import_router.post("/reimport", status_code=status.HTTP_201_CREATED)
async def start_reimport(body: ReimportSubmitRequest, store: ImportStoreDep) -> ImportJob:
    """Enqueue a library-mode reimport (`beet import -L`) of the entries matching `query`.

    The job runs through the same lifecycle as a path import (poll it, answer its decisions, abort it via
    the routes below). Once it ends, its `reimport_report` diffs each reimported entry's prior library data
    against the new — flagging fields that lost their value — and lists entries skipped because their files
    no longer exist on disk.
    """
    return await store.create(
        [],
        quiet=body.quiet,
        logpath=str(body.logpath) if body.logpath is not None else None,
        set_fields=body.set_fields,
        query=body.query,
        singletons=body.singletons,
        move_files=body.move_files,
        write_tags=body.write_tags,
    )


@import_router.get("/reimport/find_missing_source_path")
async def find_missing_source_path(
    beets_library: BeetsLibraryDep,
    downloader_hook: DownloaderHookDep,
    session: SessionDep,
    req_params: FindMissingSourcePathRequestParams,
) -> FindMissingSourcePathResponse:
    """Ask the configured downloader client where a library album/track was originally downloaded to.

    Only useful for entries imported outside a beetkeeper context (so no source path was recorded): the
    recovered pre-import folder is what a fresh path import of the entry needs. The entry's fields named in
    the beets config's `beetkeeper.downloader_hook.beets_field_names_to_query_param_names` become the search
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
    response = await _lookup_source_path(beets_library, downloader_hook, session, req_params)
    if response is None:
        kind = "album" if req_params.is_album else "item"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No beets {kind} with id {req_params.beets_id}."
        )
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
