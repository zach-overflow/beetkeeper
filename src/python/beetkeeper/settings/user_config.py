import json
import logging
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, FilePath, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

CONFIG_PATH_ENVVAR: Final[str] = "BEETKEEPER_CONFIG"
_LOGGER = logging.getLogger(__name__)


class ServerConfSection(BaseModel):
    """Model for the `server` subsection of the beets config's `beetkeeper` section."""

    model_config = ConfigDict(frozen=True)
    hostname: str
    port: int = Field(default=8080, gt=0)
    server_workers: int = Field(default=2, gt=0)


class DatabaseConfSection(BaseModel):
    """
    Model for the `database` subsection of the beets config's `beetkeeper` section.

    Holds the location of beetkeeper's own SQLite database (distinct from the beets library db). The file
    need not exist yet — it is created when alembic migrations are first applied (see `beetkeeper.db`).
    """

    model_config = ConfigDict(frozen=True)
    sqlite_path: Path = Field(
        description="Filesystem path to beetkeeper's SQLite db file (created on first migration)."
    )

    @property
    def resolved_sqlite_path(self) -> Path:
        """The configured path with `~` expanded and made absolute (parent dirs are NOT created here)."""
        return self.sqlite_path.expanduser().resolve()

    @property
    def async_url(self) -> str:
        """SQLAlchemy async URL (aiosqlite driver) used by the running application."""
        return f"sqlite+aiosqlite:///{self.resolved_sqlite_path}"

    @property
    def sync_url(self) -> str:
        """Plain SQLAlchemy SQLite URL — used by alembic offline (`--sql`) migration generation."""
        return f"sqlite:///{self.resolved_sqlite_path}"


class UserConfig(BaseSettings):
    """Beetkeeper's settings, read from the optional `beetkeeper` section of the beets config.

    Constructed by `load_config`. `beets_config_filepath` is the path of the beets config file itself
    (the file these settings were read from); it is set by `load_config`, NOT a value set by the user
    inside the `beetkeeper` section.
    """

    model_config = SettingsConfigDict(frozen=True)
    beets_config_filepath: FilePath
    log_level: Literal["CRITICAL", "DEBUG", "ERROR", "INFO", "NOTSET", "WARNING"]
    server: ServerConfSection
    database: DatabaseConfSection


class BeetKeeperConfigError(ValueError):
    """Raised on failures loading beetkeeper settings from the beets config's `beetkeeper` section."""

    pass


def load_config(raw_conf_path: Path) -> UserConfig:
    """Load beetkeeper settings from the beets config at `raw_conf_path`, returning a `UserConfig`.

    `raw_conf_path` is the path to the *beets* YAML config. Beetkeeper reads its own settings from that
    file's OPTIONAL top-level `beetkeeper:` mapping (a plain beets config without it is still a valid beets
    config). The beets config path itself becomes `UserConfig.beets_config_filepath`. Raises a
    `BeetKeeperConfigError` on a missing config file, a non-mapping `beetkeeper` section, or invalid settings.
    """
    conf_path = Path(raw_conf_path).resolve()
    if not conf_path.exists() or conf_path.is_dir():
        raise BeetKeeperConfigError(
            f"Beets config file does not exist. Check `{CONFIG_PATH_ENVVAR}` environment variable."
        )
    beets_config_data = YamlConfigSettingsSource(settings_cls=UserConfig, yaml_file=conf_path).yaml_data or {}
    beetkeeper_section = beets_config_data.get("beetkeeper") or {}
    if not isinstance(beetkeeper_section, dict):
        raise BeetKeeperConfigError("The beets config's optional `beetkeeper` section must be a mapping of settings.")
    try:
        # The beets config path itself is `beets_config_filepath` (no longer a user-set setting); a stray
        # `beets_config_filepath` inside the `beetkeeper` section is overridden by the loaded path.
        return UserConfig(**{**beetkeeper_section, "beets_config_filepath": conf_path})
    except ValidationError as e:
        # `default=str` since error `input` values include the injected `beets_config_filepath` Path.
        _LOGGER.exception(
            "Beetkeeper settings (beets config `beetkeeper` section) have problems: "
            + json.dumps(e.errors(), indent=2, default=str)
        )
        raise BeetKeeperConfigError(
            "Beetkeeper settings in the beets config's `beetkeeper` section have errors (see above)."
        ) from e
    except ValueError as e:
        _LOGGER.exception("Ran into error while loading beetkeeper settings from the beets config.")
        raise BeetKeeperConfigError(
            "Beetkeeper settings in the beets config's `beetkeeper` section have errors (see above)."
        ) from e
