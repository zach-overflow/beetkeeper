"""Tests for `make_engine`'s per-connection SQLite configuration (see `db/session.py`).

Every connection the engine hands out must carry beetkeeper's non-default settings: foreign-key
enforcement ON, WAL journaling, and synchronous=NORMAL. Asserted through a real session against a
migrated temp DB, so the test covers the `connect` event wiring, not just the pragma statements.
"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("pragma", "expected"),
    [
        ("foreign_keys", 1),
        ("journal_mode", "wal"),
        ("synchronous", 1),  # 1 == NORMAL (default is 2 == FULL)
    ],
)
async def test_engine_connections_carry_configured_pragmas(
    session_factory: async_sessionmaker[AsyncSession], pragma: str, expected: int | str
) -> None:
    async with session_factory() as session:
        value = (await session.execute(text(f"PRAGMA {pragma}"))).scalar()
    assert value == expected


@pytest.mark.anyio
async def test_wal_mode_persists_in_the_database_file(
    session_factory: async_sessionmaker[AsyncSession], db_file: Path
) -> None:
    """WAL is a persistent database-file property: a plain connection (no hook) still sees it."""
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))

    plain = sqlite3.connect(db_file)
    try:
        assert plain.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        plain.close()
