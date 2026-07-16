"""
Async SQLAlchemy/SQLModel engine + session wiring for beetkeeper's own SQLite database.

The engine is built from `UserConfig.database` at application startup (see
`beetkeeper.api.fastapi_app.lifespan`) and stored on `app.state`, so request handlers obtain a session
through the `get_session` dependency rather than via a module-global engine. Every new DB-API connection
gets beetkeeper's non-default SQLite settings via a `connect` event hook (see
`_configure_sqlite_connection`): foreign-key enforcement, WAL journaling, and `synchronous=NORMAL`.

Schema creation is owned by alembic (see `beetkeeper.db.migrations`); `SQLModel.metadata.create_all` is
intentionally avoided at runtime so the migrations stay the single source of truth.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Final, cast

from anyio import CancelScope
from fastapi import Depends, Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# aiosqlite runs the underlying sqlite3 connection in a worker thread, so disable the same-thread check.
_CONNECT_ARGS: Final[dict[str, Any]] = {"check_same_thread": False}


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    """`connect` event hook applying beetkeeper's non-default SQLite settings to each new connection.

    * `foreign_keys=ON` — SQLite does not enforce foreign keys by default; needed for the ON DELETE
      CASCADEs in the schema.
    * `journal_mode=WAL` — readers and the writer stop blocking each other (the import worker's output
      flushes run concurrently with UI polling reads). Persistent in the db file, but re-issuing it per
      connection is idempotent and covers fresh/restored files. Requires all users of the file to be on
      one host and does not work on network filesystems: https://sqlite.org/wal.html
    * `synchronous=NORMAL` — the WAL-recommended pairing (fsync only at checkpoints). A power loss can
      roll back the last transactions but cannot corrupt the database; acceptable for bookkeeping data,
      and interrupted import jobs are already handled by orphan recovery.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def make_engine(async_url: str, *, echo: bool = False) -> AsyncEngine:
    """Creates an async SQLite engine (aiosqlite); `_configure_sqlite_connection` runs per connection.

    `pool_pre_ping` (SQLAlchemy's documented "pessimistic disconnect handling") heals the pool after a
    task is cancelled mid-query: cancellation leaves that aiosqlite connection permanently broken, raising
    "no active connection" — which the aiosqlite dialect's `is_disconnect` explicitly classifies as a
    disconnect, so the ping discards the poisoned connection instead of handing it to the next checkout.
    See https://docs.sqlalchemy.org/en/20/core/pooling.html#disconnect-handling-pessimistic
    """
    engine = create_async_engine(async_url, echo=echo, connect_args=_CONNECT_ARGS, pool_pre_ping=True)
    event.listen(engine.sync_engine, "connect", _configure_sqlite_connection)
    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Builds an `async_sessionmaker` bound to `engine` (expire_on_commit off so results survive commit)."""
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def shielded_session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession]:
    """A session whose whole scope is shielded from task cancellation — for short, self-contained ops.

    Cancellation landing mid-query permanently breaks the pooled aiosqlite connection ("no active
    connection" from then on); SQLAlchemy's guidance is that in-flight DB work must be shielded from
    cancellation (https://github.com/sqlalchemy/sqlalchemy/issues/8145 — its own `terminate()` uses
    `asyncio.shield`), and `pool_pre_ping` above only heals the damage after the fact. The shield delays
    cancellation until the block exits, so keep the body tiny; do NOT use this in `get_session`, where it
    would shield the entire request handler.
    """
    with CancelScope(shield=True):
        async with sessionmaker() as session:
            yield session


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding an `AsyncSession` from the app-state sessionmaker created at startup."""
    sessionmaker = cast("async_sessionmaker[AsyncSession]", request.app.state.db_sessionmaker)
    async with sessionmaker() as session:
        yield session


# Annotated dependency for route signatures (the async analogue of the SQLModel `SessionDep` pattern:
# https://sqlmodel.tiangolo.com/tutorial/fastapi/session-with-dependency/#use-the-dependency).
SessionDep = Annotated[AsyncSession, Depends(get_session)]
