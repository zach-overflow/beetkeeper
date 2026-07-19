"""
State + data-transfer types for interactive beets import jobs.

An import is modeled as a long-running *job* that the leader-elected import worker
(`beetkeeper.core.import_worker`) runs one at a time. While beets' pipeline is mid-import it may need a
user decision (which candidate match to apply, how to resolve a duplicate); the worker publishes a
`DecisionRequest`, the job parks in `AWAITING_DECISION`, and the UI answers with an `ImportDecision`.

This module deliberately imports NO beets internals — these are plain DTOs. Mapping to/from beets'
`Action`/`AlbumMatch` types happens in `import_worker`; persistence + cross-process coordination live in
`import_store` (backed by the `ImportJobRecord`/`ImportLock` tables).
"""

import logging
import os
from datetime import datetime
from enum import StrEnum, unique

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

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def source_label(self) -> str:
        """Display name for the import source: the basename(s) of the path(s) (e.g. the album folder)."""
        return ", ".join(os.path.basename(path.rstrip("/")) or path for path in self.paths)
