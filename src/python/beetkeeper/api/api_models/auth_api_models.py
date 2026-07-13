from typing import Literal

from pydantic import BaseModel, SecretStr


class LoginRequestBody(BaseModel):
    username: SecretStr
    password: SecretStr


class LoginResponseBody(BaseModel):
    """The raw bearer token the client must send back as `Authorization: Bearer <token>` (`str`, not
    `SecretStr` — this response is the one place the token is intentionally revealed)."""

    token: str
    token_type: Literal["bearer"] = "bearer"


class LogoutResponseBody(BaseModel):
    detail: str = "Logged out."
