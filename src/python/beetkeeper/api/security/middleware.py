"""ASGI middleware enforcing beetkeeper's opt-in bearer-token login protection.

Enforcement lives at the middleware level so every router (JSON API, HTMX fragments, pages) is covered
without per-route dependencies. The check is a no-op unless `beetkeeper.auth.enable_login_protection` is
set in the user's config (read off `app.state`, which the lifespan populates).

The session token is accepted from either the `Authorization: Bearer` header (API clients) or the
`SESSION_COOKIE_NAME` HttpOnly cookie set by the `/login` browser flow. Unauthenticated failures are
shaped per caller: JSON 401 for `/api/*`, an `HX-Redirect` for in-flight HTMX fragment swaps, and a plain
redirect to `/login` for full-page browser navigation.
"""

from typing import TYPE_CHECKING, Final, cast
from urllib.parse import urlencode, urlsplit

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, RedirectResponse, Response

from beetkeeper.api.security.auth_sessions import SESSION_COOKIE_NAME, AuthSessionStore, extract_bearer_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from beetkeeper.settings import UserConfig

# Reachable without a token: the login endpoints (there is no other way to get a token), the OpenAPI
# docs, container/uptime health checks, and the non-sensitive static assets those pages load.
_EXEMPT_PATHS: Final[frozenset[str]] = frozenset(
    {"/api/auth/login", "/login", "/api/health", "/docs", "/redoc", "/openapi.json"}
)
_EXEMPT_PATH_PREFIXES: Final[tuple[str, ...]] = ("/static/",)


class LoginProtectionMiddleware(BaseHTTPMiddleware):
    """Rejects requests lacking a valid session token when login protection is enabled."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user_config = cast("UserConfig | None", getattr(request.app.state, "user_config", None))
        if user_config is None or not user_config.auth.enable_login_protection:
            return await call_next(request)
        if request.url.path in _EXEMPT_PATHS or request.url.path.startswith(_EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        token = extract_bearer_token(request.headers.get("Authorization")) or request.cookies.get(SESSION_COOKIE_NAME)
        if token is not None:
            sessionmaker = cast("async_sessionmaker[AsyncSession]", request.app.state.db_sessionmaker)
            if await AuthSessionStore(sessionmaker).is_token_valid(token):
                return await call_next(request)
        return _unauthenticated_response(request)


def _unauthenticated_response(request: Request) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            content={"detail": "Not authenticated. Obtain a bearer token via POST /api/auth/login."},
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if request.headers.get("HX-Request") == "true":
        # Swapping a redirect's login-page HTML into a fragment target would corrupt the page; HTMX honors
        # `HX-Redirect` by navigating the whole browser window instead: https://htmx.org/reference/#response_headers
        # The request URL here is the fragment endpoint, not a renderable page, so the post-login
        # destination comes from the page the browser was on (HTMX's `HX-Current-URL` header).
        current_url = urlsplit(request.headers.get("HX-Current-URL", ""))
        return Response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"HX-Redirect": _login_url(current_url.path, current_url.query)},
        )
    return RedirectResponse(url=_login_url(request.url.path, request.url.query), status_code=status.HTTP_302_FOUND)


def _login_url(next_path: str, next_query: str) -> str:
    """The `/login` URL, carrying the original destination in `?next=` so the login flow can return to it."""
    destination = next_path + (f"?{next_query}" if next_query else "")
    if not destination or destination == "/":
        return "/login"
    return "/login?" + urlencode({"next": destination})
