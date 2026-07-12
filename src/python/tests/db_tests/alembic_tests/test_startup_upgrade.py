"""Tests for `migrations.startup_upgrade` — the hands-off schema upgrade run by `beetkeeper run`.

Synchronous tests (like the rest of the alembic tests): the alembic helpers drive their own event loop
internally for the async-online path, so they must not be invoked from within an anyio test loop.
"""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from beetkeeper.db import migrations


@pytest.fixture
def base_revision(alembic_cfg: Config) -> str:
    """The id of the very first migration revision (a valid, non-head 'stale schema' target)."""
    base = ScriptDirectory.from_config(alembic_cfg).get_base()
    assert base is not None
    return base


@pytest.fixture
def head_revision(alembic_cfg: Config) -> str:
    head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
    assert head is not None
    return head


def _backup_files(db_file: Path) -> list[Path]:
    return sorted(db_file.parent.glob("*.bak"))


def test_fresh_db_upgrades_to_head_without_backup(alembic_cfg: Config, db_file: Path, head_revision: str) -> None:
    migrations.startup_upgrade(alembic_cfg, sqlite_path=db_file, auto_upgrade=True)
    assert migrations.current_revision(alembic_cfg) == head_revision
    assert not _backup_files(db_file)


def test_missing_parent_dirs_are_created(tmp_path: Path, head_revision: str) -> None:
    nested_db_file = tmp_path / "does" / "not" / "exist" / "beetkeeper.db"
    cfg = migrations.make_alembic_config(
        async_url=f"sqlite+aiosqlite:///{nested_db_file}", sync_url=f"sqlite:///{nested_db_file}"
    )
    migrations.startup_upgrade(cfg, sqlite_path=nested_db_file, auto_upgrade=True)
    assert migrations.current_revision(cfg) == head_revision


@pytest.mark.parametrize("auto_upgrade", [True, False])
def test_up_to_date_db_is_a_noop(alembic_cfg: Config, db_file: Path, auto_upgrade: bool) -> None:
    migrations.upgrade(alembic_cfg, "head")
    migrations.startup_upgrade(alembic_cfg, sqlite_path=db_file, auto_upgrade=auto_upgrade)
    assert not _backup_files(db_file)


def test_stale_db_is_backed_up_then_upgraded(
    alembic_cfg: Config, db_file: Path, base_revision: str, head_revision: str
) -> None:
    migrations.upgrade(alembic_cfg, base_revision)
    migrations.startup_upgrade(alembic_cfg, sqlite_path=db_file, auto_upgrade=True)
    assert migrations.current_revision(alembic_cfg) == head_revision
    backup_files = _backup_files(db_file)
    assert backup_files == [db_file.with_name(f"{db_file.name}.pre-{base_revision}.bak")]
    backup_cfg = migrations.make_alembic_config(
        async_url=f"sqlite+aiosqlite:///{backup_files[0]}", sync_url=f"sqlite:///{backup_files[0]}"
    )
    assert migrations.current_revision(backup_cfg) == base_revision


def test_stale_db_with_auto_upgrade_disabled_fails_untouched(
    alembic_cfg: Config, db_file: Path, base_revision: str
) -> None:
    migrations.upgrade(alembic_cfg, base_revision)
    with pytest.raises(migrations.MigrationStateError, match="beetkeeper db upgrade"):
        migrations.startup_upgrade(alembic_cfg, sqlite_path=db_file, auto_upgrade=False)
    assert migrations.current_revision(alembic_cfg) == base_revision
    assert not _backup_files(db_file)


@pytest.mark.parametrize("auto_upgrade", [True, False])
def test_db_from_newer_beetkeeper_fails_untouched(
    alembic_cfg: Config, db_file: Path, sync_url: str, auto_upgrade: bool
) -> None:
    migrations.upgrade(alembic_cfg, "head")
    engine = sa.create_engine(sync_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("UPDATE alembic_version SET version_num = 'ffffffffffff'"))
    finally:
        engine.dispose()
    with pytest.raises(migrations.MigrationStateError, match="newer beetkeeper"):
        migrations.startup_upgrade(alembic_cfg, sqlite_path=db_file, auto_upgrade=auto_upgrade)
    assert migrations.current_revision(alembic_cfg) == "ffffffffffff"
    assert not _backup_files(db_file)
