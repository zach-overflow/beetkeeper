"""Shared api_tests fixtures: a fresh `create_app()` app, an ASGI-transport async client, and overrides.

Per FastAPI's testing guidance, dependencies are swapped via `app.dependency_overrides` and requests run
fully in-process over `httpx.ASGITransport` (no sockets, no lifespan side effects). Test modules customize
the app by overriding the `app_dependency_overrides` fixture; the shared `client` fixture does the rest.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.api import create_app
from beetkeeper.core import BeetsLibrary, ImportStore

SessionOverride = Callable[[], AsyncIterator[AsyncSession]]

DependencyOverrides = dict[Callable[..., object], Callable[..., object]]


@pytest.fixture
def app_dependency_overrides() -> DependencyOverrides:
    """No overrides by default; test modules redefine this fixture to swap route dependencies."""
    return {}


@pytest.fixture
def app(app_dependency_overrides: DependencyOverrides) -> FastAPI:
    """A fresh app per test (no shared `dependency_overrides` state to clean up between tests)."""
    application = create_app()
    application.dependency_overrides.update(app_dependency_overrides)
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testclient") as http_client:
        yield http_client


@pytest.fixture
def get_session_override(session_factory: async_sessionmaker[AsyncSession]) -> SessionOverride:
    """A `get_session`-compatible dependency drawing sessions from the migrated temp DB."""

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    return _override_get_session


@pytest.fixture
def import_store(session_factory: async_sessionmaker[AsyncSession]) -> ImportStore:
    """An `ImportStore` bound to the migrated temp DB (no import worker runs)."""
    return ImportStore(session_factory)


@pytest.fixture
def beets_library(tmp_path: Path) -> BeetsLibrary:
    """A `BeetsLibrary` pointed at a fresh, empty throwaway beets config (no music files, no network)."""
    beets_config = tmp_path / "beets.yaml"
    beets_config.write_text(f"library: {tmp_path}/lib.db\ndirectory: {tmp_path}/music\n")
    return BeetsLibrary(beets_config)


@pytest.fixture
def beets_import_config() -> Iterator[Any]:
    """Yield beets' global `import` config view, restoring every key the import tests touch afterwards."""
    from beets import config

    originals = {key: config["import"][key].get() for key in ("quiet", "group_albums", "flat", "log", "set_fields")}
    try:
        yield config["import"]
    finally:
        for key, value in originals.items():
            config["import"][key] = value


@pytest.fixture
def pushed_at() -> str:
    """A fixed, timezone-aware ISO timestamp for event payloads."""
    return datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC).isoformat()
