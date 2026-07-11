"""
RESTful (JSON) endpoints to drive interactive beets imports.

Job state lives in the cross-process DB-backed `ImportStore`; the leader-elected `ImportWorker`
(`beetkeeper.core.import_worker`) runs the actual beets import. These routes only read/write the store, so
they work on any uvicorn process. HTML/HTMX equivalents live in `ui_routes.import_ui_fragments_router`.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from beetkeeper.api.api_models import ImportSubmitRequest
from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import ImportStoreDep
from beetkeeper.core import ImportDecision, ImportJob

_LOGGER = logging.getLogger(__name__)
import_router = APIRouter(prefix="/import", tags=[RouteTag.IMPORT])


@import_router.post("", status_code=status.HTTP_201_CREATED)
async def start_import(body: ImportSubmitRequest, store: ImportStoreDep) -> ImportJob:
    """Enqueue an import of the given paths and return the created (PENDING) job.

    Set `quiet=true` to import non-interactively (the `beet import -q` equivalent): no decision prompts.
    """
    return await store.create(body.paths, quiet=body.quiet)


@import_router.get("")
async def list_imports(store: ImportStoreDep) -> list[ImportJob]:
    """List all known import jobs."""
    return await store.list()


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
