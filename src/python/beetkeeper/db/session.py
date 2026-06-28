"""
Async SQLAlchemy/SQLModel engine + session wiring for beetkeeper's own SQLite database.

The engine is built from `UserConfig.database` at application startup (see
`beetkeeper.api.fastapi_app.lifespan`) and stored on `app.state`, so request handlers obtain a session
through the `get_session` dependency rather than via a module-global engine. SQLite does NOT enforce
foreign keys by default, so a `PRAGMA foreign_keys=ON` is issued on every new DB-API connection.

Schema creation is owned by alembic (see `beetkeeper.db.migrations`); `SQLModel.metadata.create_all` is
intentionally avoided at runtime so the migrations stay the single source of truth.
"""

from collections.abc import AsyncGenerator
from typing import Annotated, Any, Final, cast

from fastapi import Depends, Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# aiosqlite runs the underlying sqlite3 connection in a worker thread, so disable the same-thread check.
_CONNECT_ARGS: Final[dict[str, Any]] = {"check_same_thread": False}


def _enable_sqlite_fks(dbapi_connection: Any, _connection_record: Any) -> None:
    """`connect` event hook enabling SQLite foreign-key enforcement (needed for the ON DELETE CASCADEs)."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def make_engine(async_url: str, *, echo: bool = False) -> AsyncEngine:
    """Creates an async SQLite engine (aiosqlite) with foreign-key enforcement enabled per connection."""
    engine = create_async_engine(async_url, echo=echo, connect_args=_CONNECT_ARGS)
    event.listen(engine.sync_engine, "connect", _enable_sqlite_fks)
    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Builds an `async_sessionmaker` bound to `engine` (expire_on_commit off so results survive commit)."""
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding an `AsyncSession` from the app-state sessionmaker created at startup."""
    sessionmaker = cast("async_sessionmaker[AsyncSession]", request.app.state.db_sessionmaker)
    async with sessionmaker() as session:
        yield session


# Annotated dependency for route signatures (the async analogue of the SQLModel `SessionDep` pattern:
# https://sqlmodel.tiangolo.com/tutorial/fastapi/session-with-dependency/#use-the-dependency).
SessionDep = Annotated[AsyncSession, Depends(get_session)]
