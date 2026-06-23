import json
import logging
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, FilePath, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

CONFIG_PATH_ENVVAR: Final[str] = "BEETKEEPER_CONFIG"
_LOGGER = logging.getLogger(__name__)


class UserConfig(BaseSettings):
    """Wrapper pydantic model for the user configuration (read from yaml)."""

    model_config = SettingsConfigDict(frozen=True)
    beets_config_filepath: FilePath  # Must be an actual file that exists
    log_level: Literal["CRITICAL", "DEBUG", "ERROR", "INFO", "NOTSET", "WARNING"]
    server: ServerConfSection

    # TODO[Claude]: implement the ``UserConfig`` class definition (and subsequently, the yaml schema).
    # TODO[Claude]: add fields the rest of the app already needs but cannot source today:
    #   - a database connection URL / SQLite path (consumed by `beetkeeper.db` + alembic env.py).
    #   - the beets config/library location (used to populate `app.state.beets_config`; see
    #     `beetkeeper.api.fastapi_app.lifespan`) once the beets-integration model is decided.
    #   - if authentication is in scope (see `config_router`'s placeholder `/login/access-token`),
    #     any auth/secret settings; otherwise document that the app is unauthenticated single-user.


class ServerConfSection(BaseModel):
    """Model for the `server` section of the user config YAML file."""

    model_config = ConfigDict(frozen=True)
    hostname: str
    port: int = Field(default=8080, gt=0)
    server_workers: int = Field(default=2, gt=0)


class BeetKeeperConfigError(ValueError):
    """Raised on failures when loading the user's yaml config."""

    pass


def load_config(raw_conf_path: Path) -> UserConfig:
    """Loads the yaml config file as a `UserConfig` instance and returns it. Raises a `BeetKeeperConfigError` o/w."""
    conf_path = Path(raw_conf_path).resolve()
    if not conf_path.exists() or conf_path.is_dir():
        raise BeetKeeperConfigError(f"Config file does not exist. Check `{CONFIG_PATH_ENVVAR}` environment variable.")
    try:
        return UserConfig(**YamlConfigSettingsSource(settings_cls=UserConfig, yaml_file=conf_path).yaml_data)
    except ValidationError as e:
        _LOGGER.exception("User config has the following problems: " + json.dumps(e.errors(), indent=2))
        raise BeetKeeperConfigError("User config has errors (see list above).") from e
    except ValueError as e:
        _LOGGER.exception("Ran into error while loading user config.")
        raise BeetKeeperConfigError("User config has errors (see list above).") from e
