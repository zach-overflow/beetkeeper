import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)
query_router = APIRouter(prefix="/query")


@query_router.post("/login/access-token")
async def foo(request: Request) -> JSONResponse:
    _LOGGER.info("Replace this endpoint")
    return JSONResponse(content={}, status_code=200)
