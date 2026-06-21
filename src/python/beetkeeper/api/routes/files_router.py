import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)
files_router = APIRouter(prefix="/import")


@files_router.post("/fake")
async def foo(request: Request) -> JSONResponse:
    _LOGGER.info("Replace this endpoint")
    return JSONResponse(content={}, status_code=200)
