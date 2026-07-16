import json
import logging
from pathlib import Path
from typing import Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FilePath, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

# beets' own convention: `BEETSDIR` names the *directory* holding the beets config, and the config file
# within it is `config.yaml`. Beetkeeper follows the same scheme (and reads its settings from that file's
# optional `beetkeeper` section).
BEETS_DIR_ENVVAR: Final[str] = "BEETSDIR"
BEETS_CONFIG_FILENAME: Final[str] = "config.yaml"
_LOGGER = logging.getLogger(__name__)


class BeetKeeperConfigError(ValueError):
    """Raised on failures loading beetkeeper settings from the beets config's `beetkeeper` section."""

    pass


class ServerConfSection(BaseModel):
    """Model for the `server` subsection of the beets config's `beetkeeper` section.

    beetkeeper always runs as a single server worker process: both its own SQLite database and the beets
    library are effectively single-writer, and in-process coordination (e.g. the beets write limiter)
    depends on there being exactly one process. The former `server_workers` setting was removed; a config
    still carrying it loads fine (the key is ignored) with a deprecation warning.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")
    hostname: str
    port: int = Field(default=8337, gt=0)

    @model_validator(mode="before")
    @classmethod
    def _warn_on_removed_server_workers(cls, data: Any) -> Any:
        if isinstance(data, dict) and "server_workers" in data:
            _LOGGER.warning(
                "`beetkeeper.server.server_workers` has been removed and is ignored: beetkeeper always "
                "runs a single server worker process. Remove the key from your config."
            )
        return data


class AuthConfSection(BaseModel):
    """
    Model for the optional `auth` subsection of the beets config's `beetkeeper` section.

    Beetkeeper is single-user: when `enable_login_protection` is on, every request (outside a small exempt
    set — see `beetkeeper.api.security`) must carry a bearer token obtained from `POST /api/auth/login`
    using the `username`/`password` configured here.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")
    enable_login_protection: bool = Field(
        default=False,
        description="Opt-in: when true, all routes require a bearer token from a successful `/api/auth/login`.",
    )
    username: SecretStr | None = Field(default=None)
    password: SecretStr | None = Field(default=None)
    session_ttl_hours: int = Field(
        default=24 * 7, gt=0, description="How long a login token stays valid before a new login is required."
    )

    @model_validator(mode="after")
    def credentials_required_when_protected(self) -> Self:
        if self.enable_login_protection and (self.username is None or self.password is None):
            raise BeetKeeperConfigError(
                "`beetkeeper.auth.enable_login_protection` is on, so `beetkeeper.auth.username` and "
                "`beetkeeper.auth.password` must both be set."
            )
        return self


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
    auto_upgrade: bool = Field(
        default=True,
        description=(
            "When true (default), `beetkeeper run` applies any pending schema migrations automatically at "
            "startup (backing up the db file first). When false, a stale schema fails startup with a prompt "
            "to run `beetkeeper db upgrade` manually."
        ),
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
    auth: AuthConfSection = AuthConfSection()

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
    conf_path = Path(raw_conf_path).expanduser().resolve()
    app_conf_data = YamlConfigSettingsSource(settings_cls=UserConfig, yaml_file=conf_path).yaml_data.get("beetkeeper")
    if not app_conf_data:
        raise BeetKeeperConfigError("Invalid beets config: missing required `beetkeeper` section.")
    app_conf_data["beets_config_filepath"] = conf_path
    return app_conf_data
