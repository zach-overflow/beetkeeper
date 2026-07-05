import json
import logging
from pathlib import Path
from typing import Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FilePath, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

CONFIG_PATH_ENVVAR: Final[str] = "BEETKEEPER_CONFIG"
_LOGGER = logging.getLogger(__name__)


class BeetKeeperConfigError(ValueError):
    """Raised on failures loading beetkeeper settings from the beets config's `beetkeeper` section."""

    pass


class ServerConfSection(BaseModel):
    """Model for the `server` subsection of the beets config's `beetkeeper` section."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    hostname: str
    port: int = Field(default=8337, gt=0)
    server_workers: int = Field(default=2, gt=0)


class DatabaseConfSection(BaseModel):
    """
    Model for the `database` subsection of the beets config's `beetkeeper` section.

    Holds the location of beetkeeper's own SQLite database (distinct from the beets library db). The file
    need not exist yet — it is created when alembic migrations are first applied (see `beetkeeper.db`).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")
    sqlite_path: Path = Field(
        description="Filesystem path to beetkeeper's SQLite db file. NOTE: this is must be a different file than beets' `library.db`."
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
    """
    Beetkeeper's settings, read from the `beetkeeper` section of the beets config.
    Constructed via `load_config` from the file at `beets_config_filepath`.
    """

    model_config = SettingsConfigDict(frozen=True, extra="ignore")
    beets_config_filepath: FilePath
    log_level: Literal["CRITICAL", "DEBUG", "ERROR", "INFO", "NOTSET", "WARNING"]
    server: ServerConfSection
    database: DatabaseConfSection

    @model_validator(mode="after")
    def final_config_checks(self) -> Self:
        """Runs any checks which can only happen after all subsection fields are loaded and individually validated."""
        if self.database.resolved_sqlite_path == self.beets_config_filepath:
            raise BeetKeeperConfigError(
                "`beetkeeper.database.sqlite_path` and beets' library.db must have different paths."
            )
        return self


def load_config(raw_conf_path: Path) -> UserConfig:
    """Load beetkeeper settings from the beets config at `raw_conf_path`, returning a `UserConfig`.

    `raw_conf_path` is the path to the *beets* YAML config. Beetkeeper reads its own settings from that
    file's top-level `beetkeeper:` mapping. The beets config path itself becomes `UserConfig.beets_config_filepath`. Raises a
    `BeetKeeperConfigError` on a missing config file, or bad settings.
    """
    try:
        return UserConfig(**_load_app_conf_data(raw_conf_path=raw_conf_path))
    except ValidationError as e:
        err_msg_prefix = "Beetkeeper is misconfigured. Beets' `beetkeeper` config section has problem(s). "
        _LOGGER.exception(err_msg_prefix + f"See below:\n{json.dumps(e.errors(), indent=2, default=str)}")
        raise BeetKeeperConfigError(err_msg_prefix + "See above.") from e
    except ValueError as e:
        raise BeetKeeperConfigError("Failed to load beets' `beetkeeper` config section (see above for errors).") from e


def _load_app_conf_data(raw_conf_path: Path) -> dict[str, Any]:
    """Loads and returns the raw dict of YAML data under the `beetkeeper` config section."""
    if not raw_conf_path.exists() or raw_conf_path.is_dir():
        raise BeetKeeperConfigError(f"Beets config file '{str(raw_conf_path)}' does not exist.")
    conf_path = Path(raw_conf_path).resolve()
    app_conf_data = YamlConfigSettingsSource(settings_cls=UserConfig, yaml_file=conf_path).yaml_data.get("beetkeeper")
    if not app_conf_data:
        raise BeetKeeperConfigError("Invalid beets config: missing required `beetkeeper` section.")
    app_conf_data["beets_config_filepath"] = conf_path
    return app_conf_data
