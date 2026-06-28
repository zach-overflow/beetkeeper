"""Shared fixtures: anyio backend selection, temp-file SQLite URLs, an alembic Config, and a migrated DB."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.db import make_engine, make_sessionmaker, migrations


@pytest.fixture
def anyio_backend() -> str:
    """Run all `@pytest.mark.anyio` tests on asyncio (we do not target trio). See CLAUDE.md test rules."""
    return "asyncio"


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """A throwaway SQLite file path under pytest's tmp_path (the file is created by the migrations)."""
    return tmp_path / "beetkeeper_test.db"


@pytest.fixture
def async_url(db_file: Path) -> str:
    return f"sqlite+aiosqlite:///{db_file}"


@pytest.fixture
def sync_url(db_file: Path) -> str:
    return f"sqlite:///{db_file}"


@pytest.fixture
def alembic_cfg(async_url: str, sync_url: str) -> Config:
    """An alembic Config for the packaged environment, pointed at the temp DB."""
    return migrations.make_alembic_config(async_url=async_url, sync_url=sync_url)


@pytest.fixture
def migrated_db(alembic_cfg: Config, async_url: str) -> str:
    """Applies all migrations to a fresh temp DB and returns its async (aiosqlite) URL."""
    migrations.upgrade(alembic_cfg, "head")
    return async_url


@pytest.fixture
async def session_factory(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """An `async_sessionmaker` bound to a freshly-migrated temp DB (FK enforcement enabled)."""
    engine = make_engine(migrated_db)
    try:
        yield make_sessionmaker(engine)
    finally:
        await engine.dispose()
