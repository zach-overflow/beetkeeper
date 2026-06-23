import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)
config_router = APIRouter(prefix="/config")


# TODO[Claude]: decide whether authentication is in scope. This `/login/access-token` placeholder is lifted
#     from the full-stack-fastapi template and implies JWT auth, but CLAUDE.md never specifies auth, users,
#     or whether beetkeeper is single-user self-hosted. Either design auth (and move it to a dedicated
#     auth router with backing `UserConfig`/secret settings) or remove this and document "no auth".
@config_router.post("/login/access-token")
async def foo(request: Request) -> JSONResponse:
    _LOGGER.info("Replace this endpoint")
    return JSONResponse(content={}, status_code=200)
