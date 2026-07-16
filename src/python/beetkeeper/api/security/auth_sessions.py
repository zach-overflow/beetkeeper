"""DB-backed bearer-token session store for beetkeeper's opt-in login protection.

Tokens are opaque `secrets.token_urlsafe` strings handed out by `POST /api/auth/login`; only their SHA-256
digests are persisted (see `beetkeeper.db.models.AuthSessionRecord`), so the DB is the cross-worker source
of truth without ever storing a usable credential.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col

from beetkeeper.db.models import AuthSessionRecord
from beetkeeper.db.session import shielded_session
from beetkeeper.settings import AuthConfSection

_TOKEN_NUM_BYTES = 32

# Browser flow: `POST /login` stores the same session token in this HttpOnly cookie, since browsers cannot
# attach `Authorization` headers on their own. SameSite=Lax (set where the cookie is issued) is the CSRF
# guard appropriate for a single-user self-hosted app.
SESSION_COOKIE_NAME: Final[str] = "beetkeeper_session"


def credentials_match(username: str, password: str, auth_config: AuthConfSection) -> bool:
    """Constant-time comparison of submitted credentials against the configured `beetkeeper.auth` pair."""
    if auth_config.username is None or auth_config.password is None:
        return False
    username_ok = secrets.compare_digest(username.encode(), auth_config.username.get_secret_value().encode())
    password_ok = secrets.compare_digest(password.encode(), auth_config.password.get_secret_value().encode())
    return username_ok and password_ok


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """Return the token from an `Authorization: Bearer <token>` header value, or `None` if absent/malformed."""
    if authorization_header is None:
        return None
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a raw bearer token — the only form of the token ever persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    """Naive UTC now, matching how the DB's `DateTime` columns are stored (see `core.import_store`)."""
    return datetime.now(UTC).replace(tzinfo=None)


class AuthSessionStore:
    """Creates, validates, and revokes login sessions against the `auth_session` table."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        """Bind the store to the app's shared `async_sessionmaker`."""
        self._sessionmaker = sessionmaker

    async def open_session(self, ttl: timedelta) -> str:
        """Persist a new session valid for `ttl` and return its raw bearer token (never stored)."""
        token = secrets.token_urlsafe(_TOKEN_NUM_BYTES)
        now = _utcnow()
        async with shielded_session(self._sessionmaker) as session:
            await session.execute(delete(AuthSessionRecord).where(col(AuthSessionRecord.expires_at) <= now))
            session.add(AuthSessionRecord(token_hash=hash_token(token), created_at=now, expires_at=now + ttl))
            await session.commit()
        return token

    async def is_token_valid(self, token: str) -> bool:
        """True if `token` matches an unexpired session."""
        async with shielded_session(self._sessionmaker) as session:
            record = await session.get(AuthSessionRecord, hash_token(token))
        return record is not None and record.expires_at > _utcnow()

    async def revoke_token(self, token: str) -> bool:
        """Delete the session for `token` (logout). Returns whether a session existed."""
        async with shielded_session(self._sessionmaker) as session:
            result: Any = await session.execute(
                delete(AuthSessionRecord).where(col(AuthSessionRecord.token_hash) == hash_token(token))
            )
            await session.commit()
        return bool(result.rowcount)
