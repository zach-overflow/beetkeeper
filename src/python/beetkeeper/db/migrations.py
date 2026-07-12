"""
Programmatic alembic integration for beetkeeper.

Builds an alembic `Config` pointed at the migration environment shipped inside the package
(`db/alembic/`) WITHOUT requiring the `alembic.ini` file at runtime, and runs migrations online (connect
+ apply) or offline (`--sql`, emit DDL to stdout without a DB connection). Both the `beetkeeper db ...`
CLI subcommands (see `beetkeeper.main`) and the test-suite go through these helpers.

Offline mode reference: https://alembic.sqlalchemy.org/en/latest/offline.html
"""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Final

import sqlalchemy as sa
from alembic import command, util
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from beetkeeper.settings import UserConfig

_ALEMBIC_DIR: Final[Path] = Path(__file__).resolve().parent / "alembic"
_LOGGER = logging.getLogger(__name__)


class MigrationStateError(RuntimeError):
    """Raised when the database's migration state prevents the server from starting."""


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


def current_revision(cfg: Config) -> str | None:
    """Returns the database's stamped alembic revision (`None` for a fresh/unstamped database)."""
    sync_url = cfg.get_main_option(SYNC_URL_OPT)
    if not sync_url:
        raise ValueError(f"alembic Config is missing the '{SYNC_URL_OPT}' option.")
    engine = sa.create_engine(sync_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def startup_upgrade(cfg: Config, *, sqlite_path: Path, auto_upgrade: bool) -> None:
    """Brings the database schema to head before the server starts serving.

    No-op when the schema is already current. Otherwise the SQLite file (if it exists) is backed up
    alongside itself first, then `upgrade head` is applied — so a fresh install and a version upgrade are
    the same, hands-off code path. Raises `MigrationStateError` instead of touching the database when the
    stamped revision is unknown to this beetkeeper version (i.e. the file was written by a *newer*
    beetkeeper — downgrades are never applied automatically), or when migrations are pending but
    `auto_upgrade` is disabled.
    """
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    db_file_exists = sqlite_path.exists()
    current = current_revision(cfg)
    script_dir = ScriptDirectory.from_config(cfg)
    if current == script_dir.get_current_head():
        return
    if current is not None:
        try:
            script_dir.get_revision(current)
        except util.CommandError as e:
            raise MigrationStateError(
                f"The database at '{sqlite_path}' is stamped with schema revision '{current}', which this "
                "beetkeeper version does not know about — it was likely written by a newer beetkeeper. "
                "Refusing to start (downgrades are never applied automatically); upgrade beetkeeper instead."
            ) from e
    if not auto_upgrade:
        raise MigrationStateError(
            f"The database at '{sqlite_path}' is behind this beetkeeper version and `database.auto_upgrade` "
            "is disabled. Run `beetkeeper db upgrade`, then start the server again."
        )
    if db_file_exists:
        backup_path = _backup_sqlite_file(sqlite_path, current)
        _LOGGER.info("Backed up '%s' to '%s' before applying schema migrations.", sqlite_path, backup_path)
    upgrade(cfg, "head")
    _LOGGER.info("Database schema migrated to head (previous revision: %s).", current or "<empty database>")


def _backup_sqlite_file(sqlite_path: Path, current: str | None) -> Path:
    """Copies the SQLite db via sqlite's backup API to `<name>.pre-<revision>.bak` next to the original."""
    backup_path = sqlite_path.with_name(f"{sqlite_path.name}.pre-{current or 'unstamped'}.bak")
    with closing(sqlite3.connect(sqlite_path)) as source, closing(sqlite3.connect(backup_path)) as target:
        source.backup(target)
    return backup_path
