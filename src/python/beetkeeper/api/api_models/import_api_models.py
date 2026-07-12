"""Request/response models for the `/api/import` endpoints (see `beetkeeper.core.import_worker`)."""

from functools import partial
from pathlib import Path

from beets import config
from pydantic import BaseModel, ConfigDict, Field


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
