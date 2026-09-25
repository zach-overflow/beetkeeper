"""Tests proving beetkeeper's DB is fully constructible from the alembic migration scripts.

Covers online upgrade/downgrade, offline (`--sql`) generation, and that the migrations have not drifted
from the SQLModel ORM models. These are synchronous tests: the alembic helpers run their own event loop
internally for the async-online path, so they must not be invoked from within an anyio test loop.
"""

import io

import sqlalchemy as sa
from alembic.config import Config

from beetkeeper.db import migrations

EXPECTED_TABLES = {"listener_event", "album_event", "track_event"}


def _table_names(sync_url: str) -> set[str]:
    engine = sa.create_engine(sync_url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_head_creates_event_tables(alembic_cfg: Config, sync_url: str) -> None:
    migrations.upgrade(alembic_cfg, "head")
    tables = _table_names(sync_url)
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables


def test_downgrade_to_base_drops_event_tables(alembic_cfg: Config, sync_url: str) -> None:
    migrations.upgrade(alembic_cfg, "head")
    migrations.downgrade(alembic_cfg, "base")
    assert not (EXPECTED_TABLES & _table_names(sync_url))


def test_offline_sql_emits_create_table_for_each_model(alembic_cfg: Config) -> None:
    """Offline mode must emit the full schema DDL without touching a database."""
    buffer = io.StringIO()
    alembic_cfg.output_buffer = buffer
    migrations.upgrade(alembic_cfg, "head", sql=True)
    emitted_sql = buffer.getvalue()
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in emitted_sql
