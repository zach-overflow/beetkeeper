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
from beetkeeper.db.session import get_session
from beetkeeper.settings import UserConfig, load_config

SessionOverride = Callable[[], AsyncIterator[AsyncSession]]

DependencyOverrides = dict[Callable[..., object], Callable[..., object]]

AUTH_TEST_USERNAME = "admin"
AUTH_TEST_PASSWORD = "correct-horse-battery-staple"


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
def enable_login_protection(request: pytest.FixtureRequest) -> bool:
    """Enabled by default; auth tests opt out via indirect parametrization."""
    return bool(getattr(request, "param", True))


@pytest.fixture
def auth_user_config(tmp_path: Path, db_file: Path, enable_login_protection: bool) -> UserConfig:
    """A `UserConfig` whose `auth` section carries the test credentials (protection on unless opted out)."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "directory: /music\n"
        "library: /lib.db\n"
        "beetkeeper:\n"
        "  log_level: INFO\n"
        "  server:\n"
        "    hostname: 127.0.0.1\n"
        f"  database:\n    sqlite_path: {db_file}\n"
        "  auth:\n"
        f"    enable_login_protection: {str(enable_login_protection).lower()}\n"
        f"    username: {AUTH_TEST_USERNAME}\n"
        f"    password: {AUTH_TEST_PASSWORD}\n",
        encoding="utf-8",
    )
    return load_config(config_path)


@pytest.fixture
async def auth_app(
    auth_user_config: UserConfig,
    session_factory: async_sessionmaker[AsyncSession],
    get_session_override: SessionOverride,
) -> FastAPI:
    """A fresh app with the state the lifespan would normally set (config + sessionmaker on `app.state`).

    The auth middleware and session store read straight off `app.state` (no dependency-override seam), so
    auth test modules alias their `app` fixture to this instead of the plain `app` above.
    """
    application = create_app()
    application.state.user_config = auth_user_config
    application.state.db_sessionmaker = session_factory
    application.dependency_overrides[get_session] = get_session_override
    return application


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
