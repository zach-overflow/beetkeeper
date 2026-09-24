"""Shared FastAPI dependencies for the API + UI routers."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

from beetkeeper.api.security import AuthSessionStore
from beetkeeper.core import BeetsLibrary, ImportStore
from beetkeeper.hooks import DownloaderHook
from beetkeeper.settings import DownloaderHookConfSection, UserConfig

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_user_config(request: Request) -> UserConfig:
    """Return the `UserConfig` loaded at startup (see `beetkeeper.api.fastapi_app`)."""
    return cast("UserConfig", request.app.state.user_config)


UserConfigDep = Annotated[UserConfig, Depends(get_user_config)]


def get_beets_library(user_config: UserConfigDep) -> BeetsLibrary:
    """Return a `BeetsLibrary` adapter bound to the configured beets library (read from `UserConfig`)."""
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


def get_auth_session_store(request: Request) -> AuthSessionStore:
    """Return a DB-backed `AuthSessionStore` over the app's sessionmaker (login sessions are cross-worker)."""
    sessionmaker = cast("async_sessionmaker[AsyncSession]", request.app.state.db_sessionmaker)
    return AuthSessionStore(sessionmaker)


AuthSessionStoreDep = Annotated[AuthSessionStore, Depends(get_auth_session_store)]


def get_downloader_hook(request: Request) -> DownloaderHook:
    """
    Returns the `DownloaderHook` instance set on the application lifespan. Used to fetch missing source filepath
    information from the downloader client, if configured. An app running without the lifespan (tests) gets
    a disabled hook, so routes that only consult `enabled` need no override.
    """
    hook = getattr(request.app.state, "downloader_hook", None)
    if hook is None:
        hook = DownloaderHook(DownloaderHookConfSection(), Path("/downloads"))
        request.app.state.downloader_hook = hook
    return cast("DownloaderHook", hook)


DownloaderHookDep = Annotated[DownloaderHook, Depends(get_downloader_hook)]
