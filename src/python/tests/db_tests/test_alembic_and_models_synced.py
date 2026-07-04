"""Guardrails ensuring the alembic migration history stays in sync with the SQLModel ORM models.

If a test here fails after you edit `beetkeeper.db.models`, you almost certainly forgot to add a
migration — see `src/python/beetkeeper/db/README.md` for how to generate one.

These are synchronous tests (no anyio): they reflect the migrated schema with a plain sync engine and
compare it against `SQLModel.metadata`.
"""

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

from beetkeeper.db import migrations

# Tables that alembic itself manages (not derived from our models); excluded from model-sync comparisons.
_ALEMBIC_BOOKKEEPING_TABLES = {"alembic_version"}


def test_single_alembic_head(alembic_cfg: Config) -> None:
    """Exactly one head revision — multiple heads mean an unmerged branch that `upgrade head` can't resolve."""
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    assert len(script_dir.get_heads()) == 1


def test_revision_history_is_walkable(alembic_cfg: Config) -> None:
    """The full down_revision chain resolves from head back to base without missing/cyclic revisions."""
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    revisions = list(script_dir.walk_revisions("base", "heads"))
    assert revisions, "no migration revisions found"
    assert revisions[-1].down_revision is None


def test_no_pending_autogenerate_diff(alembic_cfg: Config, sync_url: str) -> None:
    """The core check: after `upgrade head`, autogenerate detects no difference between DB and models."""
    migrations.upgrade(alembic_cfg, "head")
    engine = sa.create_engine(sync_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"target_metadata": SQLModel.metadata})
            diffs = compare_metadata(context, SQLModel.metadata)
    finally:
        engine.dispose()
    assert diffs == [], f"Models and migrations are out of sync — a migration is missing for: {diffs}"


def test_migrated_tables_match_models(alembic_cfg: Config, sync_url: str) -> None:
    """Every model table (and no extra non-bookkeeping table) exists after migrating to head."""
    migrations.upgrade(alembic_cfg, "head")
    engine = sa.create_engine(sync_url)
    try:
        reflected_tables = set(sa.inspect(engine).get_table_names()) - _ALEMBIC_BOOKKEEPING_TABLES
    finally:
        engine.dispose()
    assert reflected_tables == set(SQLModel.metadata.tables.keys())


def test_migrated_columns_match_models(alembic_cfg: Config, sync_url: str) -> None:
    """Each migrated table's columns match its model's columns (catches a model column with no migration)."""
    migrations.upgrade(alembic_cfg, "head")
    engine = sa.create_engine(sync_url)
    try:
        inspector = sa.inspect(engine)
        for table_name, table in SQLModel.metadata.tables.items():
            reflected_columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert reflected_columns == set(table.columns.keys()), f"Column mismatch in table '{table_name}'"
    finally:
        engine.dispose()
