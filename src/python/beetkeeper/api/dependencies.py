"""Shared FastAPI dependencies for the API + UI routers."""

from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

from beetkeeper.core import BeetsLibrary, ImportStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from beetkeeper.settings import UserConfig


def get_beets_library(request: Request) -> BeetsLibrary:
    """Return a `BeetsLibrary` adapter bound to the configured beets library (read from `UserConfig`)."""
    user_config = cast("UserConfig", request.app.state.user_config)
    return BeetsLibrary(user_config.beets_config_filepath)


BeetsLibraryDep = Annotated[BeetsLibrary, Depends(get_beets_library)]


def get_import_store(request: Request) -> ImportStore:
    """Return a DB-backed `ImportStore` over the app's sessionmaker (created in the lifespan).

    The store is the cross-process source of truth for import jobs, so route handlers use it (not the
    per-process `ImportWorker`) to submit/poll/answer/abort — see `beetkeeper.api.fastapi_app`.
    """
    sessionmaker = cast("async_sessionmaker[AsyncSession]", request.app.state.db_sessionmaker)
    return ImportStore(sessionmaker)


ImportStoreDep = Annotated[ImportStore, Depends(get_import_store)]
