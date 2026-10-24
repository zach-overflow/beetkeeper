"""Request/response models for the `/api/import` endpoints (see `beetkeeper.core.import_worker`)."""

from functools import partial
from pathlib import Path
from typing import Annotated, Self

from beets import config
from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from beetkeeper.api.constants import LibrarySubject
from beetkeeper.core import CleanSlateTarget
from beetkeeper.hooks import DownloaderSearchResult


def import_config_flag(key: str) -> bool:
    """Read a boolean from beets' `import` config section (beets ships a default for every key we read)."""
    try:
        return bool(config["import"][key].get(bool))
    except Exception:  # config missing/unreadable — fall back to beets' shipped default (all are "no")
        return False


def import_config_set_fields() -> dict[str, str]:
    """Read beets' `import.set_fields` config as a plain `field -> value` str dict (empty when unset)."""
    try:
        raw = config["import"]["set_fields"].get() or {}
        return {str(key): str(value) for key, value in raw.items()}
    except Exception:  # config missing/unreadable — behave as if no set-fields are configured
        return {}


def import_config_logpath() -> Path | None:
    """Resolve beets' `import.log` config to a filesystem path (None when unset, matching beets)."""
    try:
        return Path(config["import"]["log"].as_filename()) if config["import"]["log"].get() else None
    except Exception:  # config missing/unreadable — behave as if no log path is configured
        return None


class ImportSubmitRequest(BaseModel):
    """
    Body for starting an import: the filesystem path(s) beets should import. All default values come from the
    `beets.config` values (cached) if left unspecified.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    paths: list[str] = Field(min_length=1, description="One or more paths (files/dirs) to import.")
    quiet: bool = Field(
        default_factory=partial(import_config_flag, "quiet"),
        description=(
            "Run non-interactively (like `beet import -q`): never prompt. Strong matches are applied "
            "automatically; anything else falls back to beets' `quiet_fallback` config (skip by default)."
        ),
    )
    logpath: Path | None = Field(
        default_factory=import_config_logpath,
        description="Corresponds to the `-l` option when running an import command, or config's `import.log` option. See https://beets.readthedocs.io/en/stable/reference/cli.html#import",
    )
    group_albums: bool = Field(
        default_factory=partial(import_config_flag, "group_albums"),
        description="See https://beets.readthedocs.io/en/stable/reference/config.html#group-albums",
    )
    flat: bool = Field(
        default_factory=partial(import_config_flag, "flat"),
        description="Corresponds to the `--flat` flag when running an import command. See https://beets.readthedocs.io/en/stable/reference/cli.html#import",
    )
    set_fields: dict[str, str] = Field(
        default_factory=import_config_set_fields,
        description="Corresponds to the `--set field=value` option for beets' `import` CLI command. Can set multiple key-value pairs.",
    )


class LibraryEntryRef(BaseModel):
    """Names one beets library entry by exactly one of its album id or its item (track) id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    beets_album_id: int | None = Field(
        default=None, description="The beets library id of an album. Mutually exclusive with `beets_item_id`."
    )
    beets_item_id: int | None = Field(
        default=None, description="The beets library id of an item (track). Mutually exclusive with `beets_album_id`."
    )

    @model_validator(mode="after")
    def validate_mutually_exclusive_beets_ids(self) -> Self:
        """Enforces that the request must have exactly one of `beets_album_id` or `beets_item_id` set."""
        err_msg_prefix = "Exactly 1 of 'beets_album_id' or 'beets_item_id' must be set"
        if self.beets_album_id is None and self.beets_item_id is None:
            raise ValueError(f"{err_msg_prefix}, but neither was provided.")
        if self.beets_album_id is not None and self.beets_item_id is not None:
            raise ValueError(f"{err_msg_prefix}, but both were provided.")
        return self

    @property
    def is_album(self) -> bool:
        """`True` if this request names an album. `False` if it names a beets item."""
        return self.beets_album_id is not None

    @property
    def subject(self) -> LibrarySubject:
        """The kind of library entry the provided id names."""
        return LibrarySubject.ALBUM if self.is_album else LibrarySubject.TRACK

    @property
    def beets_id(self) -> int:
        """The one id that was provided."""
        beets_id = self.beets_album_id if self.is_album else self.beets_item_id
        assert beets_id is not None  # guaranteed by the validator
        return beets_id

    @property
    def clean_slate_target(self) -> CleanSlateTarget:
        """The entry as a clean-slate target."""
        return CleanSlateTarget.from_ids(self.beets_album_id, self.beets_item_id)


class FindMissingSourcePathRequest(LibraryEntryRef):
    """Body of `POST /api/import/find_missing_source_path`: the entry to ask the downloader about."""


class CleanSlatePreviewRequest(LibraryEntryRef):
    """Query parameters of `GET /api/import/clean_slate/preview`: the entry to remove and its source folder."""

    source_path: str = Field(
        min_length=1,
        description=(
            "The entry's raw (pre-import) source folder, under beetkeeper's `downloads_path`; for a standalone "
            "track, the audio file itself or a folder holding just that file."
        ),
    )
    allow_fewer_files: bool = Field(
        default=False,
        description=(
            "Proceed even when the source holds fewer audio files than the entry currently has on disk (the "
            "clean slate would then delete files the source cannot replace). Off by default."
        ),
    )


CleanSlatePreviewParams = Annotated[CleanSlatePreviewRequest, Query()]


class CleanSlateSubmitRequest(CleanSlatePreviewRequest):
    """
    Body for starting a clean-slate import: remove the named library entry — its rows, the files inside the
    beets directory and the album art, like `beet remove -d` — then import `source_path` afresh as an ordinary
    path import (decisions, abort, quiet mode all apply). Nothing is carried over from the old entry — not its
    flexible attributes, not its added-date — except the flexible attributes named as keys of the
    `downloader_hook.beet_field_to_dl_search_field` config, whose values are re-applied to the fresh import via
    `set_fields` (winning over a `set_fields` entry of the same name). Option defaults come from the
    `beets.config` values.

    The removal happens before the import starts; skipping or aborting the import afterwards leaves the entry
    removed and the source files where they are. Preview first with `GET /api/import/clean_slate/preview`.
    """

    quiet: bool = Field(
        default_factory=partial(import_config_flag, "quiet"),
        description="Run non-interactively (like `beet import -q`). See `ImportSubmitRequest.quiet`.",
    )
    logpath: Path | None = Field(
        default_factory=import_config_logpath,
        description="Corresponds to the `-l` option, or the config's `import.log` option.",
    )
    set_fields: dict[str, str] = Field(
        default_factory=import_config_set_fields,
        description="Corresponds to the `--set field=value` option for beets' `import` CLI command.",
    )


class FindMissingSourcePathResponse(BaseModel):
    """Response model for the `/find_missing_source_path` endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    found_match: bool = Field(description="True if the missing source path search returned a matching result.")
    search_status_code: int | None = Field(
        default=None, description="The HTTP status code of the downloader API search, when one was made."
    )
    source_directory: str | None = Field(
        default=None,
        description="The source directory (as mounted on the app container) from the matched search, if any.",
    )
    query_params: dict[str, str] = Field(
        default_factory=dict, description="The query params the search was made with (the renamed beets fields)."
    )
    detail: str = Field(default="", description="Why no match was found, when `found_match` is false.")
    recorded_inference: bool = Field(
        default=False,
        description=(
            "True when the match was stored as the entry's *inferred* source path (shown as such on the search "
            "page; kept apart from source paths recorded from the beetkeeper plugin's events)."
        ),
    )

    @classmethod
    def from_search(
        cls, result: DownloaderSearchResult, query_params: dict[str, str], *, recorded_inference: bool = False
    ) -> Self:
        """Build the response from the downloader hook's search result."""
        return cls(
            found_match=result.found,
            search_status_code=result.status_code,
            source_directory=result.source_path,
            query_params=query_params,
            detail=result.detail,
            recorded_inference=recorded_inference,
        )
