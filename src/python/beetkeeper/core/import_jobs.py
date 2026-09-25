"""
State + data-transfer types for interactive beets import jobs.

An import is modeled as a long-running *job* that the leader-elected import worker
(`beetkeeper.core.import_worker`) runs one at a time. While beets' pipeline is mid-import it may need a
user decision (which candidate match to apply, how to resolve a duplicate); the worker publishes a
`DecisionRequest`, the job parks in `AWAITING_DECISION`, and the UI answers with an `ImportDecision`.

A job is a path import, optionally preceded by a *clean slate*: the removal of one existing library entry
(`ImportJob.clean_slate_album_id` / `clean_slate_item_id`) before its raw source folder is imported afresh
(see `beetkeeper.core.clean_slate`). `CleanSlatePreview` is the read-only dry run of that removal.

This module deliberately imports NO beets internals — these are plain DTOs. Mapping to/from beets'
`Action`/`AlbumMatch` types happens in `import_worker`; persistence + cross-process coordination live in
`import_store` (backed by the `ImportJobRecord`/`ImportLock` tables).
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, unique
from typing import Literal, Self

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


CleanSlateSubject = Literal["album", "track"]


@dataclass(frozen=True)
class CleanSlateTarget:
    """The library entry a clean slate removes: an album, or a standalone track."""

    subject: CleanSlateSubject
    beets_id: int

    @classmethod
    def from_ids(cls, album_id: int | None, item_id: int | None) -> Self:
        """Build the target from a job's `clean_slate_album_id` / `clean_slate_item_id` (exactly one set)."""
        if (album_id is None) == (item_id is None):
            raise ValueError("Exactly one of album_id or item_id must be given.")
        if album_id is not None:
            return cls("album", album_id)
        assert item_id is not None
        return cls("track", item_id)


class CleanSlatePreview(BaseModel):
    """The dry run of a clean-slate import: what removing the library entry and importing its source would do.

    Produced read-only by `core.clean_slate.preview` for the API/UI preview, and again by the worker as the
    guard before it removes anything. `errors` lists the conditions that block the job outright; `warnings`
    are worth a look but do not block. `needs_confirmation` is set when the source folder holds fewer audio
    files than the entry currently has on disk — proceeding would delete files the source cannot replace,
    so the caller must opt in explicitly (`allow_fewer_files`).
    """

    model_config = ConfigDict(frozen=True)
    subject: CleanSlateSubject
    beets_id: int
    label: str = Field(description="`albumartist - album` for an album, `artist - title` for a standalone track.")
    item_count: int = Field(description="Library rows the entry holds (1 for a standalone track).")
    files_present: int = Field(description="How many of those rows still have their file on disk.")
    missing_paths: list[str] = Field(default_factory=list, description="Library paths whose file is gone.")
    expected_tracks: int | None = Field(
        default=None, description="Track total the album's tags claim (beets' `albumtotal`), when known."
    )
    files_to_delete: list[str] = Field(
        default_factory=list, description="Library files the removal deletes (inside the beets directory)."
    )
    files_kept_outside_library: list[str] = Field(
        default_factory=list, description="Entry files left on disk because they live outside the beets directory."
    )
    art_to_delete: str | None = Field(default=None, description="The album art file the removal deletes, if any.")
    flexible_attributes_lost: list[str] = Field(
        default_factory=list,
        description="Flexible attribute names on the entry that a clean slate does not keep (`fields_preserved` aside).",
    )
    fields_preserved: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The entry's flexible attributes named as keys of the `downloader_hook.beet_field_to_dl_search_field` "
            "config, with their values: re-applied to the fresh import via beets' `--set`."
        ),
    )
    source_path: str
    source_audio_files: int = Field(default=0, description="Readable audio files found under the source path.")
    source_album_groups: int = Field(default=0, description="Album folders beets would import from the source.")
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    needs_confirmation: bool = Field(
        default=False,
        description="The source has fewer audio files than the entry has on disk and `allow_fewer_files` was not set.",
    )

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def ok(self) -> bool:
        """Whether the clean slate may run as previewed (no blocking error and no outstanding confirmation)."""
        return not self.errors and not self.needs_confirmation

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def files_missing(self) -> int:
        """How many of the entry's rows point at a file that no longer exists."""
        return self.item_count - self.files_present


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
    # Clean slate: the library album (or standalone track) removed before `paths` (its source folder) is
    # imported. At most one is set; both None means a plain path import.
    clean_slate_album_id: int | None = None
    clean_slate_item_id: int | None = None
    # The submitter's opt-in to a source holding fewer audio files than the entry has on disk (see
    # `CleanSlatePreview.needs_confirmation`); the worker re-runs the preview with it before removing anything.
    clean_slate_allow_fewer_files: bool = False

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def is_clean_slate(self) -> bool:
        """Whether this job removes an existing library entry before importing its source afresh."""
        return self.clean_slate_album_id is not None or self.clean_slate_item_id is not None

    @computed_field  # type: ignore[prop-decorator]  # mypy limitation: @computed_field stacks on @property
    @property
    def source_label(self) -> str:
        """Display name for the import source: the path basename(s), prefixed for a clean-slate import."""
        label = ", ".join(os.path.basename(path.rstrip("/")) or path for path in self.paths)
        return f"clean slate: {label}" if self.is_clean_slate else label
