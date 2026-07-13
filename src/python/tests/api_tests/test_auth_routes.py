"""Tests for `/api/auth` login/logout and the `LoginProtectionMiddleware` bearer-token gate.

The auth fixtures (`auth_app` + config/credentials) live in this package's `conftest.py`, shared with the
browser cookie-flow tests in `test_auth_ui.py`.
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from .conftest import AUTH_TEST_PASSWORD as _PASSWORD
from .conftest import AUTH_TEST_USERNAME as _USERNAME


@pytest.fixture
def app(auth_app: FastAPI) -> FastAPI:
    return auth_app


async def _login(client: AsyncClient, username: str = _USERNAME, password: str = _PASSWORD) -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_login_returns_usable_bearer_token(client: AsyncClient) -> None:
    response = await client.post("/api/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["token"], str) and len(body["token"]) > 20


@pytest.mark.anyio
@pytest.mark.parametrize(("username", "password"), [(_USERNAME, "wrong-password"), ("wrong-user", _PASSWORD), ("", "")])
async def test_login_rejects_bad_credentials(client: AsyncClient, username: str, password: str) -> None:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_protected_route_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/events")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
@pytest.mark.parametrize("bad_header", ["Basic dXNlcjpwYXNz", "Bearer ", "Bearer not-a-real-token"])
async def test_protected_route_rejects_invalid_authorization_headers(client: AsyncClient, bad_header: str) -> None:
    response = await client.get("/api/events", headers={"Authorization": bad_header})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_valid_token_grants_access(client: AsyncClient) -> None:
    token = await _login(client)
    response = await client.get("/api/events", headers=_bearer(token))
    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("exempt_path", ["/api/health", "/openapi.json", "/docs"])
async def test_exempt_paths_are_reachable_without_token(client: AsyncClient, exempt_path: str) -> None:
    response = await client.get(exempt_path)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_logout_revokes_the_token(client: AsyncClient) -> None:
    token = await _login(client)
    assert (await client.get("/api/events", headers=_bearer(token))).status_code == 200

    logout_response = await client.post("/api/auth/logout", headers=_bearer(token))
    assert logout_response.status_code == 200
    assert logout_response.json() == {"detail": "Logged out."}

    assert (await client.get("/api/events", headers=_bearer(token))).status_code == 401


@pytest.mark.anyio
async def test_logout_only_revokes_its_own_token(client: AsyncClient) -> None:
    first_token = await _login(client)
    second_token = await _login(client)
    assert (await client.post("/api/auth/logout", headers=_bearer(first_token))).status_code == 200
    assert (await client.get("/api/events", headers=_bearer(first_token))).status_code == 401
    assert (await client.get("/api/events", headers=_bearer(second_token))).status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("enable_login_protection", [False], indirect=True)
async def test_disabled_protection_leaves_routes_open(client: AsyncClient) -> None:
    response = await client.get("/api/events")
    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("enable_login_protection", [False], indirect=True)
async def test_login_returns_403_when_protection_disabled(client: AsyncClient) -> None:
    response = await client.post("/api/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
    assert response.status_code == 403
