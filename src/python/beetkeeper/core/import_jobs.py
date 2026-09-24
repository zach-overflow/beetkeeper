"""
State + data-transfer types for interactive beets import jobs.

An import is modeled as a long-running *job* that the leader-elected import worker
(`beetkeeper.core.import_worker`) runs one at a time. While beets' pipeline is mid-import it may need a
user decision (which candidate match to apply, how to resolve a duplicate); the worker publishes a
`DecisionRequest`, the job parks in `AWAITING_DECISION`, and the UI answers with an `ImportDecision`.

A job is either a path import or a library-mode *reimport* (`ImportJob.query`, the `beet import -L`
equivalent); a reimport additionally yields a `ReimportReport` diffing the prior library data against the new.

This module deliberately imports NO beets internals — these are plain DTOs. Mapping to/from beets'
`Action`/`AlbumMatch` types happens in `import_worker`; persistence + cross-process coordination live in
`import_store` (backed by the `ImportJobRecord`/`ImportLock` tables).
"""

import logging
import os
import re
from datetime import datetime
from enum import StrEnum, unique
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, computed_field

_LOGGER = logging.getLogger(__name__)


@unique
class ImportJobStatus(StrEnum):
    """Lifecycle states of an import job."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_DECISION = "awaiting_decision"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@unique
class ImportAction(StrEnum):
    """beetkeeper-side mirror of beets' import `action` choices (decoupled from beets internals)."""

    APPLY = "apply"
    ASIS = "asis"  # import without changing tags
    SKIP = "skip"
    # TODO[Claude]: extend + map to `beets.importer.action.*` in `import_worker` as the flow grows
    #     (e.g. as-tracks, group-albums, manual id/search). Keep this enum the API-facing contract.


class ImportCandidate(BaseModel):
    """A serializable view of one beets match candidate, surfaced to the UI for selection.

    Beyond the headline `label`/`similarity`, the optional release attributes below let the UI tell
    otherwise-identical candidates apart (e.g. different pressings/editions of the same album); `details`
    joins the populated ones into a single human-readable line for display.
    """

    model_config = ConfigDict(frozen=True)
    index: int
    label: str
    similarity: float | None = Field(default=None, description="1.0 - beets match distance, if available.")
    data_source: str | None = None
    year: int | None = None
    country: str | None = None
    media: str | None = None
    record_label: str | None = None
    catalognum: str | None = None
    disambiguation: str | None = None
    track_count: int | None = None
    album_id: str | None = Field(default=None, description="Source-specific release id (e.g. a MusicBrainz MBID).")
    release_url: str | None = Field(
        default=None, description="Web URL for the release, from the source plugin (beets' `AlbumInfo.data_url`)."
    )

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def details(self) -> str:
        """One-line summary of the differentiating attributes (empty string when none are known)."""
        release = self.record_label or ""
        if self.catalognum:
            release = f"{release} [{self.catalognum}]".strip() if release else f"[{self.catalognum}]"
        parts = [
            part
            for part in (
                str(self.year) if self.year else None,
                self.country,
                self.media,
                release or None,
                f"{self.track_count} tracks" if self.track_count else None,
                self.data_source,
                self.disambiguation,
            )
            if part
        ]
        return " · ".join(parts)


class DecisionRequest(BaseModel):
    """Published when the importer needs a user choice for a task; the matching `ImportDecision` unblocks it."""

    model_config = ConfigDict(frozen=True)
    job_id: str
    task_id: str
    prompt: str
    candidates: list[ImportCandidate] = Field(default_factory=list)
    allowed_actions: list[ImportAction] = Field(default_factory=list)


class ImportDecision(BaseModel):
    """The user's answer to a `DecisionRequest` (posted back from the UI)."""

    model_config = ConfigDict(frozen=True)
    action: ImportAction
    candidate_index: int | None = Field(default=None, description="Required when `action` is APPLY.")


# beets formats an unset numeric field as its zero default, padded per field type (`0`, `00`, `0000`, `0.0`).
_BLANK_VALUE: Final[re.Pattern[str]] = re.compile(r"\s*(0+(\.0+)?|False)?\s*")


def is_blank_value(value: str | None) -> bool:
    """Whether a formatted beets field value carries no information (unset, empty, zero, or `False`)."""
    return value is None or _BLANK_VALUE.fullmatch(value) is not None


class FieldChange(BaseModel):
    """One library field whose value differs between the prior library entry and the reimported one."""

    model_config = ConfigDict(frozen=True)
    field: str
    old: str | None = None
    new: str | None = None

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def dropped(self) -> bool:
        """True when the reimport lost information: the field held a value before and is blank now."""
        return not is_blank_value(self.old) and is_blank_value(self.new)


class TrackChange(BaseModel):
    """The field-level changes a reimport made to one track (`path` is its pre-reimport location)."""

    model_config = ConfigDict(frozen=True)
    label: str
    path: str
    changes: list[FieldChange] = Field(default_factory=list)


class ReimportEntry(BaseModel):
    """Prior-vs-new diff for one reimported album (or singleton track).

    `shared_changes` are the changes every track has in common (album-level edits such as a corrected album
    title), hoisted out of `tracks` so they are reported once. `left_behind` lists tracks of the original
    album that the chosen match did not cover: beets leaves their library entries under the old album.
    """

    model_config = ConfigDict(frozen=True)
    label: str
    shared_changes: list[FieldChange] = Field(default_factory=list)
    tracks: list[TrackChange] = Field(default_factory=list)
    left_behind: list[str] = Field(default_factory=list)


class MissingFilesEntry(BaseModel):
    """A library album/track skipped by a reimport because its file(s) no longer exist on disk."""

    model_config = ConfigDict(frozen=True)
    label: str
    paths: list[str]


class ReimportReport(BaseModel):
    """What a library reimport changed, plus the entries it had to skip because their files are gone."""

    model_config = ConfigDict(frozen=True)
    entries: list[ReimportEntry] = Field(default_factory=list)
    missing_files: list[MissingFilesEntry] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="True when entries beyond the report cap were omitted.")


class ImportJob(BaseModel):
    """API-facing view of a single import job (the persisted record is `db.models.ImportJobRecord`)."""

    id: str
    status: ImportJobStatus
    paths: list[str]
    created_at: datetime
    error: str | None = None
    pending_decision: DecisionRequest | None = None
    # True once the UI has answered the pending decision but the worker hasn't consumed it yet. The UI uses
    # this to keep polling (the job is momentarily still AWAITING_DECISION) instead of re-showing the prompt.
    decision_submitted: bool = False
    # Human-readable, append-only log of the import's progress, surfaced on the job's UI fragment.
    output: str | None = None
    # Non-interactive (`beet import -q`) mode: the worker auto-decides matches instead of prompting.
    quiet: bool = False
    # Per-job import settings mirroring `beet import` flags (`-l`, `--group-albums`, `--flat`, `--set`).
    logpath: str | None = None
    group_albums: bool = False
    flat: bool = False
    set_fields: dict[str, str] = Field(default_factory=dict)
    # Library-mode reimport (`beet import -L`): beets query parts selecting the library entries to reimport.
    # None means a regular path import; an empty list matches the entire library.
    query: list[str] | None = None
    singletons: bool = False
    # Reimport file handling; None defers to the beets config. `move_files=False` is `-C -M` (retag in place).
    move_files: bool | None = None
    write_tags: bool | None = None
    reimport_report: ReimportReport | None = None

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def is_reimport(self) -> bool:
        """Whether this job reimports existing library entries (library mode) instead of importing paths."""
        return self.query is not None

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def source_label(self) -> str:
        """Display name for the import source: the path basename(s), or the library query for a reimport."""
        if self.query is not None:
            return f"reimport: {' '.join(self.query)}" if self.query else "reimport: entire library"
        return ", ".join(os.path.basename(path.rstrip("/")) or path for path in self.paths)
