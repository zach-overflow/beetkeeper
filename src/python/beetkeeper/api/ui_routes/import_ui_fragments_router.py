"""
HTMX fragment routes for the interactive import flow.

These return HTML partials (not JSON) for the `/import` page:
  * `POST /fragment/import`                    — start an import from the page form, render the job fragment.
  * `GET  /fragment/import/{job_id}`           — poll a job's current state (the fragment self-refreshes).
  * `POST /fragment/import/{job_id}/decision`  — answer the match decision the job is parked on.
  * `POST /fragment/import/{job_id}/abort`     — cooperatively cancel a running import.

All state goes through the cross-process `ImportStore`. The single `import_job.html` fragment dispatches on
`job.status` (poll while running, show candidate buttons while awaiting a decision).
"""

import logging
import os
from collections.abc import Callable, Sequence
from typing import Annotated, Any

from anyio import Path as AsyncPath
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from beetkeeper.api.dependencies import ImportStoreDep
from beetkeeper.api.jinja_driver import get_templates
from beetkeeper.core import ImportAction, ImportCandidate, ImportDecision, ImportJob, ImportJobStatus

_LOGGER = logging.getLogger(__name__)
import_ui_fragments_router = APIRouter(prefix="/fragment/import")

_JOB_FRAGMENT = "fragment_templates/import_job.html"
_JOB_LIST_FRAGMENT = "fragment_templates/import_job_list.html"
_PATH_SUGGESTIONS_FRAGMENT = "fragment_templates/path_suggestions.html"
_ACTIVE_STATUSES = frozenset({ImportJobStatus.PENDING, ImportJobStatus.RUNNING, ImportJobStatus.AWAITING_DECISION})
_MAX_PATH_SUGGESTIONS = 25
_MAX_DIR_SCAN = 500  # hard cap on entries scanned per directory, to bound work on huge folders
# Imports are pinned to this root (the container's `/downloads` mount): autocomplete and submitted paths
# must live under it. Keep in sync with the prefilled value/pattern in `page_templates/import_page.html`.
_IMPORT_ROOT = "/downloads"


def _job_entry(job: ImportJob) -> dict[str, object]:
    """A template entry pairing a job with its pre-computed candidate table (for the list fragment)."""
    table = build_candidate_table(job.pending_decision.candidates) if job.pending_decision else None
    return {"job": job, "candidate_table": table, "settings_summary": _job_settings_summary(job)}


def _job_settings_summary(job: ImportJob) -> str:
    """One-line summary of the job's non-default import settings (empty when it uses none of them)."""
    flags = ((job.quiet, "quiet"), (job.group_albums, "group albums"), (job.flat, "flat"))
    parts = [label for enabled, label in flags if enabled]
    if job.logpath:
        parts.append(f"log: {job.logpath}")
    if job.set_fields:
        parts.append("set: " + ", ".join(f"{key}={value}" for key, value in job.set_fields.items()))
    return " · ".join(parts)


def _parse_set_fields(raw: str) -> dict[str, str]:
    """Parse the form's set-fields textarea (one `field=value` per line) into a dict; 422 on a bad line."""
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        key, separator, value = text.partition("=")
        if not separator or not key.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Set-fields line {text!r} is not of the form field=value.",
            )
        fields[key.strip()] = value.strip()
    return fields


def _under_import_root(path: str) -> bool:
    """Whether `path` is the import root or a path inside it, with any `..`/`.` segments resolved away."""
    normalized = os.path.normpath(path.strip())
    return normalized == _IMPORT_ROOT or normalized.startswith(_IMPORT_ROOT + os.sep)


async def _dir_suggestions(raw_path: str) -> list[str]:
    """Real subdirectories matching the partial path being typed, restricted to under `_IMPORT_ROOT`.

    Autocomplete is offered only for paths inside the import root (`/downloads`); anything else — or a `..`
    that would escape the root — yields no suggestions. A trailing `/` lists everything in that folder; a
    leaf filters (case-insensitively) by prefix. Only directories are returned; FS errors yield nothing.
    """
    text = raw_path.strip()
    if not _under_import_root(text):  # only browse within the import root (also blocks `..` escapes)
        return []
    if text.endswith("/"):
        parent, prefix = AsyncPath(text), ""
    elif text == _IMPORT_ROOT:
        parent, prefix = AsyncPath(_IMPORT_ROOT), ""
    else:
        typed = AsyncPath(text)
        parent, prefix = typed.parent, typed.name
    prefix_lower = prefix.lower()
    matches: list[str] = []
    scanned = 0
    try:
        async for child in parent.iterdir():
            scanned += 1
            if scanned > _MAX_DIR_SCAN:
                break
            try:
                if child.name.lower().startswith(prefix_lower) and await child.is_dir():
                    matches.append(str(child))
            except OSError:
                continue
    except OSError:
        return []
    matches.sort()
    return matches[:_MAX_PATH_SUGGESTIONS]


def _text(value: Any) -> str:
    return str(value)


def _percent(value: Any) -> str:
    return f"{float(value) * 100:.0f}%"


# Ordered candidate columns: (ImportCandidate attribute, header, text formatter, link-url attribute). A
# column is shown only when it differentiates the candidates (see `build_candidate_table`). For a "link"
# column the differing check and the cell link both use `url_attr`; its text is a plain "view".
_CANDIDATE_COLUMNS: tuple[tuple[str, str, Callable[[Any], str], str | None], ...] = (
    ("similarity", "Match", _percent, None),
    ("label", "Album", _text, None),
    ("year", "Year", _text, None),
    ("media", "Media", _text, None),
    ("record_label", "Label", _text, None),
    ("catalognum", "Catalog #", _text, None),
    ("country", "Country", _text, None),
    ("disambiguation", "Disambig.", _text, None),
    ("track_count", "Tracks", _text, None),
    ("data_source", "Source", _text, None),
    ("album_id", "Link", _text, "release_url"),
)


def build_candidate_table(candidates: Sequence[ImportCandidate]) -> dict[str, Any] | None:
    """Build a table model for the candidate chooser, one row per candidate.

    Columns are the *union of differentiating attributes*: a column is included only when the candidates
    hold more than one distinct value for it (so identical-across-all fields are hidden). For a lone
    candidate there is nothing to differentiate, so every populated attribute is shown instead. Returns
    `None` when there are no candidates. The Apply button is rendered by the template as the trailing cell.
    """
    if not candidates:
        return None

    columns = [
        spec
        for spec in _CANDIDATE_COLUMNS
        if _column_is_informative(
            [getattr(candidate, spec[0] if spec[3] is None else spec[3]) for candidate in candidates]
        )
    ]
    rows = [
        {"index": candidate.index, "cells": [_build_cell(candidate, spec) for spec in columns]}
        for candidate in candidates
    ]
    return {"headers": [header for _, header, _, _ in columns], "rows": rows}


def _column_is_informative(values: list[Any]) -> bool:
    """A column earns a place if candidates differ on it, or (single candidate) it has a value at all."""
    if len(set(values)) > 1:
        return True
    return len(values) == 1 and values[0] not in (None, "")


def _build_cell(candidate: ImportCandidate, spec: tuple[str, str, Callable[[Any], str], str | None]) -> dict[str, Any]:
    """Render one candidate's cell for `spec`: a `{text, url}` pair (url set only for link columns)."""
    attr, _header, formatter, url_attr = spec
    if url_attr is not None:
        url = getattr(candidate, url_attr)
        return {"text": "view" if url else "", "url": url}
    value = getattr(candidate, attr)
    return {"text": formatter(value) if value not in (None, "") else "", "url": None}


def _render_job(request: Request, job: ImportJob) -> HTMLResponse:
    candidate_table = build_candidate_table(job.pending_decision.candidates) if job.pending_decision else None
    context = {"job": job, "candidate_table": candidate_table, "settings_summary": _job_settings_summary(job)}
    return get_templates().TemplateResponse(request=request, name=_JOB_FRAGMENT, context=context)


async def _require_job(store: ImportStoreDep, job_id: str) -> ImportJob:
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No import job '{job_id}'.")
    return job


@import_ui_fragments_router.get("", response_class=HTMLResponse)
async def import_active_list(request: Request, store: ImportStoreDep) -> HTMLResponse:
    """Render every currently-active import job (newest first).

    The /import page loads this on page load, so ongoing / awaiting-decision jobs persist across leaving
    and returning to the page (state lives in the DB-backed store, not the page DOM).
    """
    active = [job for job in await store.list() if job.status in _ACTIVE_STATUSES]
    active.reverse()  # store.list() is oldest-first; show newest first (matches the form's prepend)
    context = {"entries": [_job_entry(job) for job in active]}
    return get_templates().TemplateResponse(request=request, name=_JOB_LIST_FRAGMENT, context=context)


@import_ui_fragments_router.post("", response_class=HTMLResponse)
async def import_submit(
    request: Request,
    store: ImportStoreDep,
    path: Annotated[str, Form()],
    quiet: Annotated[bool, Form()] = False,
    group_albums: Annotated[bool, Form()] = False,
    flat: Annotated[bool, Form()] = False,
    logpath: Annotated[str, Form()] = "",
    set_fields: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Start an import of a single path (which must live under `_IMPORT_ROOT`) and render its job fragment.

    The remaining form fields are the per-job import settings (see `ImportStore.create`); the page's form
    prefills them from the beets config, and unchecked checkboxes simply arrive absent (i.e. off).
    """
    cleaned = path.strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide a path to import.")
    if not _under_import_root(cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Import path must be under {_IMPORT_ROOT}."
        )
    job = await store.create(
        [cleaned],
        quiet=quiet,
        group_albums=group_albums,
        flat=flat,
        logpath=logpath.strip() or None,
        set_fields=_parse_set_fields(set_fields),
    )
    return _render_job(request, job)


@import_ui_fragments_router.get("/path-suggestions", response_class=HTMLResponse)
async def path_suggestions(request: Request, path: str = "") -> HTMLResponse:
    """Autocomplete `<option>`s of real subdirectories for the partial filesystem `path` being typed.

    Defined before `/{job_id}` so the literal route wins over the job-status path parameter.
    """
    context = {"paths": await _dir_suggestions(path)}
    return get_templates().TemplateResponse(request=request, name=_PATH_SUGGESTIONS_FRAGMENT, context=context)


@import_ui_fragments_router.get("/{job_id}", response_class=HTMLResponse)
async def import_job_status(request: Request, store: ImportStoreDep, job_id: str) -> HTMLResponse:
    """Render a job's current fragment (the running/pending fragment polls this endpoint)."""
    return _render_job(request, await _require_job(store, job_id))


@import_ui_fragments_router.post("/{job_id}/decision", response_class=HTMLResponse)
async def import_job_decision(
    request: Request,
    store: ImportStoreDep,
    job_id: str,
    action: Annotated[ImportAction, Form()],
    candidate_index: Annotated[int | None, Form()] = None,
) -> HTMLResponse:
    """Submit the user's match decision, then render the job's next fragment."""
    await _require_job(store, job_id)
    await store.submit_decision(job_id, ImportDecision(action=action, candidate_index=candidate_index))
    return _render_job(request, await _require_job(store, job_id))


@import_ui_fragments_router.post("/{job_id}/abort", response_class=HTMLResponse)
async def import_job_abort(request: Request, store: ImportStoreDep, job_id: str) -> HTMLResponse:
    """Cooperatively abort an in-flight import and render its fragment."""
    await _require_job(store, job_id)
    await store.request_abort(job_id)
    return _render_job(request, await _require_job(store, job_id))
