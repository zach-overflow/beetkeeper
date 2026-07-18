"""
Shared fixtures wiring the beets plugin's `_BeetKeeperClient` to an in-process FastAPI `TestClient`, so
client/server contract tests exercise real request serialization and route deserialization with no sockets
and no database (the async DB session dependency is replaced by an autospec mock).
"""

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from beetkeeper.api.fastapi_app import create_app
from beetkeeper.db.session import get_session
from beetsplug.beetkeeper_plugin.beetkeeper_plugin import _APIToken, _BeetKeeperClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from pytest_mock import MockerFixture


@pytest.fixture(scope="session")
def app_base_url() -> str:
    return "http://localhost:8337"


@pytest.fixture
def beetkeeper_fastapi_app(mocker: MockerFixture) -> FastAPI:
    """A fresh app whose DB session dependency is an autospec `AsyncSession` mock (no engine, no database)."""
    app = create_app()
    mock_session = mocker.create_autospec(AsyncSession, instance=True)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session
    return app


@pytest.fixture
def fastapi_client(beetkeeper_fastapi_app: FastAPI) -> TestClient:
    """https://fastapi.tiangolo.com/tutorial/testing/#using-testclient"""
    return TestClient(beetkeeper_fastapi_app)


@pytest.fixture
def plugin_client(mocker: MockerFixture, app_base_url: str, fastapi_client: TestClient) -> _BeetKeeperClient:
    """A real `_BeetKeeperClient` whose HTTP layer is rerouted into the in-process FastAPI test client."""

    def _request_side_effect(**kwargs: Any) -> Any:
        return fastapi_client.request(method=kwargs["method"], url=kwargs["url"], json=kwargs["json"])

    plugin_client_instance = _BeetKeeperClient(url=app_base_url, api_token=_APIToken(value="fake-token"))
    mocker.patch.object(plugin_client_instance, "request", side_effect=_request_side_effect)
    return plugin_client_instance
