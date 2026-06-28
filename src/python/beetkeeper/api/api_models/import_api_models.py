"""Request/response models for the `/api/import` endpoints (see `beetkeeper.core.import_worker`)."""

from pydantic import BaseModel, ConfigDict, Field


class ImportSubmitRequest(BaseModel):
    """Body for starting an import: the filesystem path(s) beets should import."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    paths: list[str] = Field(min_length=1, description="One or more paths (files/dirs) to import.")
    quiet: bool = Field(
        default=False,
        description=(
            "Run non-interactively (like `beet import -q`): never prompt. Strong matches are applied "
            "automatically; anything else falls back to beets' `quiet_fallback` config (skip by default)."
        ),
    )
