from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from beetkeeper.api.api_models import LoginRequestBody, LoginResponseBody, LogoutResponseBody
from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import AuthSessionStoreDep, UserConfigDep
from beetkeeper.api.security import credentials_match

auth_router = APIRouter(prefix="/auth", tags=[RouteTag.AUTH])

_bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


@auth_router.post("/login")
async def login(
    login_body: LoginRequestBody, user_config: UserConfigDep, session_store: AuthSessionStoreDep
) -> LoginResponseBody:
    """Exchange the configured `beetkeeper.auth` credentials for a bearer token."""
    auth_config = user_config.auth
    if not auth_config.enable_login_protection:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Login protection is disabled (`beetkeeper.auth.enable_login_protection`); no token is needed.",
        )
    if not credentials_match(
        login_body.username.get_secret_value(), login_body.password.get_secret_value(), auth_config
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = await session_store.open_session(ttl=timedelta(hours=auth_config.session_ttl_hours))
    return LoginResponseBody(token=token)


@auth_router.post("/logout")
async def logout(credentials: BearerCredentialsDep, session_store: AuthSessionStoreDep) -> LogoutResponseBody:
    """Revoke the bearer token this request authenticated with (identified by the `Authorization` header)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No bearer token to log out.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await session_store.revoke_token(credentials.credentials)
    return LogoutResponseBody()
