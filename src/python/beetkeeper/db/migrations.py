"""
Programmatic alembic integration for beetkeeper.

Builds an alembic `Config` pointed at the migration environment shipped inside the package
(`db/alembic/`) WITHOUT requiring the `alembic.ini` file at runtime, and runs migrations online (connect
+ apply) or offline (`--sql`, emit DDL to stdout without a DB connection). Both the `beetkeeper db ...`
CLI subcommands (see `beetkeeper.main`) and the test-suite go through these helpers.

Offline mode reference: https://alembic.sqlalchemy.org/en/latest/offline.html
"""

from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config

from beetkeeper.settings import UserConfig

_ALEMBIC_DIR: Final[Path] = Path(__file__).resolve().parent / "alembic"

# Custom alembic main-option keys read by `env.py` to resolve the connection URL for each mode. We keep
# both so the same `Config` serves online (async) runs and offline (`--sql`) generation.
ASYNC_URL_OPT: Final[str] = "beetkeeper.async_url"
SYNC_URL_OPT: Final[str] = "beetkeeper.sync_url"


def make_alembic_config(*, async_url: str, sync_url: str) -> Config:
    """Builds an alembic `Config` for the packaged environment, carrying both URLs for `env.py` to pick from."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("version_locations", str(_ALEMBIC_DIR / "versions"))
    # Use OS path separator semantics for version_locations (silences alembic's legacy-split warning).
    cfg.set_main_option("path_separator", "os")
    # `sqlalchemy.url` is alembic's default URL key; env.py prefers the explicit beetkeeper options below.
    cfg.set_main_option("sqlalchemy.url", sync_url)
    cfg.set_main_option(ASYNC_URL_OPT, async_url)
    cfg.set_main_option(SYNC_URL_OPT, sync_url)
    return cfg


def alembic_config_from_user_config(user_config: UserConfig) -> Config:
    """Builds an alembic `Config` from a loaded `UserConfig` (reads `user_config.database`)."""
    return make_alembic_config(async_url=user_config.database.async_url, sync_url=user_config.database.sync_url)


def upgrade(cfg: Config, revision: str = "head", *, sql: bool = False) -> None:
    """Applies migrations up to `revision`. When `sql=True`, runs offline and emits DDL to stdout instead."""
    command.upgrade(cfg, revision, sql=sql)


def downgrade(cfg: Config, revision: str, *, sql: bool = False) -> None:
    """Reverts migrations down to `revision` (e.g. ``base``). When `sql=True`, emits DDL to stdout instead."""
    command.downgrade(cfg, revision, sql=sql)
