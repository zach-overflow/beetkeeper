"""Browser login/logout flow: the `/login` page + form posts, backed by the same DB session store as the
JSON API (`api_routes/auth_router.py`). Successful logins set the session token as an HttpOnly cookie
(`SESSION_COOKIE_NAME`), which `LoginProtectionMiddleware` accepts alongside bearer headers."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from beetkeeper.api.dependencies import AuthSessionStoreDep, UserConfigDep
from beetkeeper.api.jinja_driver import get_templates
from beetkeeper.api.security import SESSION_COOKIE_NAME, credentials_match

auth_ui_router = APIRouter()

_LOGIN_TEMPLATE = "page_templates/login_page.html"

NextQueryParam = Annotated[str | None, Query(alias="next")]
NextFormField = Annotated[str | None, Form(alias="next")]


def _safe_next_path(raw_next: str | None) -> str:
    """Clamp a `?next=` value to a same-site path, defaulting to the site root.

    Only site-relative paths pass: anything with a scheme/host (`https://...`) or a scheme-relative
    `//host` (browsers also treat `/\\host` that way) would be an open redirect to another origin.
    """
    if raw_next and raw_next.startswith("/") and not raw_next.startswith(("//", "/\\")):
        return raw_next
    return "/"


@auth_ui_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user_config: UserConfigDep, next_path: NextQueryParam = None) -> Response:
    """Render the login form (or bounce to the site root when login protection is off).

    A `?next=` query (set by the middleware's redirect) is carried through the form as a hidden field so a
    successful login can return to the originally requested page.
    """
    if not user_config.auth.enable_login_protection:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return get_templates().TemplateResponse(
        request=request, name=_LOGIN_TEMPLATE, context={"next_path": _safe_next_path(next_path)}
    )


@auth_ui_router.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    user_config: UserConfigDep,
    session_store: AuthSessionStoreDep,
    next_path: NextFormField = None,
) -> Response:
    """Validate the form credentials, set the session cookie, and redirect to the original destination."""
    auth_config = user_config.auth
    if not auth_config.enable_login_protection:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    if not credentials_match(username, password, auth_config):
        return get_templates().TemplateResponse(
            request=request,
            name=_LOGIN_TEMPLATE,
            context={"error_message": "Incorrect username or password.", "next_path": _safe_next_path(next_path)},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token = await session_store.open_session(ttl=timedelta(hours=auth_config.session_ttl_hours))
    response = RedirectResponse(url=_safe_next_path(next_path), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=auth_config.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
    )
    return response


@auth_ui_router.post("/logout")
async def logout_submit(request: Request, session_store: AuthSessionStoreDep) -> RedirectResponse:
    """Revoke the cookie's session (if any), clear the cookie, and redirect to the login page."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is not None:
        await session_store.revoke_token(token)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response
