"""Tests for the browser login flow: the `/login` page, session-cookie issuance, and cookie-based access.

Uses the shared `auth_app` fixture (see `conftest.py`); the httpx client carries cookies across requests
like a browser would.
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from beetkeeper.api.security import SESSION_COOKIE_NAME

from .conftest import AUTH_TEST_PASSWORD as _PASSWORD
from .conftest import AUTH_TEST_USERNAME as _USERNAME


@pytest.fixture
def app(auth_app: FastAPI) -> FastAPI:
    return auth_app


async def _form_login(client: AsyncClient, username: str = _USERNAME, password: str = _PASSWORD) -> None:
    response = await client.post("/login", data={"username": username, "password": password})
    assert response.status_code == 303
    assert response.headers["Location"] == "/"


@pytest.mark.anyio
async def test_login_page_is_reachable_without_a_session(client: AsyncClient) -> None:
    response = await client.get("/login")
    assert response.status_code == 200
    assert '<form method="post" action="/login">' in response.text


@pytest.mark.anyio
async def test_unauthenticated_page_request_redirects_to_login_with_next(client: AsyncClient) -> None:
    response = await client.get("/events")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=%2Fevents"


@pytest.mark.anyio
async def test_login_redirect_preserves_the_query_string(client: AsyncClient) -> None:
    response = await client.get("/search", params={"query": "artist:Beatles"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=%2Fsearch%3Fquery%3Dartist%253ABeatles"


@pytest.mark.anyio
async def test_unauthenticated_htmx_request_gets_hx_redirect_with_page_next(client: AsyncClient) -> None:
    """The `next` of an HTMX fragment 401 is the page the browser was on (`HX-Current-URL`), not the fragment."""
    headers = {"HX-Request": "true", "HX-Current-URL": "http://testclient/import?foo=bar"}
    response = await client.get("/fragment/import/jobs", headers=headers)
    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/login?next=%2Fimport%3Ffoo%3Dbar"


@pytest.mark.anyio
async def test_unauthenticated_htmx_request_without_current_url_redirects_plainly(client: AsyncClient) -> None:
    response = await client.get("/events", headers={"HX-Request": "true"})
    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/login"


@pytest.mark.anyio
async def test_form_login_sets_cookie_and_grants_page_access(client: AsyncClient) -> None:
    await _form_login(client)
    assert SESSION_COOKIE_NAME in client.cookies

    page_response = await client.get("/events")
    assert page_response.status_code == 200
    assert 'action="/logout"' in page_response.text


@pytest.mark.anyio
async def test_session_cookie_also_works_for_api_paths(client: AsyncClient) -> None:
    await _form_login(client)
    response = await client.get("/api/events")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_form_login_with_bad_credentials_rerenders_with_error(client: AsyncClient) -> None:
    response = await client.post("/login", data={"username": _USERNAME, "password": "wrong-password"})
    assert response.status_code == 401
    assert "Incorrect username or password." in response.text
    assert SESSION_COOKIE_NAME not in client.cookies


@pytest.mark.anyio
async def test_next_survives_the_full_login_round_trip(client: AsyncClient) -> None:
    """Original request -> login redirect -> form hidden field -> post-login redirect back to the original."""
    bounce = await client.get("/import")
    login_page = await client.get(bounce.headers["Location"])
    assert '<input type="hidden" name="next" value="/import">' in login_page.text

    login_response = await client.post("/login", data={"username": _USERNAME, "password": _PASSWORD, "next": "/import"})
    assert login_response.status_code == 303
    assert login_response.headers["Location"] == "/import"
    assert (await client.get("/import")).status_code == 200


@pytest.mark.anyio
async def test_failed_login_keeps_the_next_field(client: AsyncClient) -> None:
    response = await client.post(
        "/login", data={"username": _USERNAME, "password": "wrong-password", "next": "/import"}
    )
    assert response.status_code == 401
    assert '<input type="hidden" name="next" value="/import">' in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "unsafe_next", ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)", ""]
)
async def test_unsafe_next_values_fall_back_to_the_site_root(client: AsyncClient, unsafe_next: str) -> None:
    response = await client.post("/login", data={"username": _USERNAME, "password": _PASSWORD, "next": unsafe_next})
    assert response.status_code == 303
    assert response.headers["Location"] == "/"


@pytest.mark.anyio
async def test_logout_revokes_the_session_and_clears_the_cookie(client: AsyncClient) -> None:
    await _form_login(client)
    token = client.cookies[SESSION_COOKIE_NAME]

    logout_response = await client.post("/logout")
    assert logout_response.status_code == 303
    assert logout_response.headers["Location"] == "/login"
    assert SESSION_COOKIE_NAME not in client.cookies

    assert (await client.get("/events")).status_code == 302
    revoked_bearer = await client.get("/api/events", headers={"Authorization": f"Bearer {token}"})
    assert revoked_bearer.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize("enable_login_protection", [False], indirect=True)
async def test_login_page_redirects_home_when_protection_disabled(client: AsyncClient) -> None:
    for response in (await client.get("/login"), await client.post("/login", data={"username": "x", "password": "y"})):
        assert response.status_code == 302
        assert response.headers["Location"] == "/"
