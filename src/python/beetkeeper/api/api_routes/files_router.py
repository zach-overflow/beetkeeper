import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)
# TODO[Claude]: prefix collides with `import_router` (also `prefix="/import"`); both mount under `/api`,
#     so their routes overlap. This is almost certainly meant to be `prefix="/files"`.
files_router = APIRouter(prefix="/import")


@files_router.post("/fake")
async def foo(request: Request) -> JSONResponse:
    _LOGGER.info("Replace this endpoint")
    return JSONResponse(content={}, status_code=200)
