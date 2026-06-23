import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)
import_router = APIRouter(prefix="/import")


# TODO[Claude]: placeholder `POST /fake` named `foo`. Replace with real import endpoints. Note `files_router`
#     currently also uses `prefix="/import"` and collides with this router (see its TODO).
@import_router.post("/fake")
async def foo(request: Request) -> JSONResponse:
    _LOGGER.info("Replace this endpoint")
    return JSONResponse(content={}, status_code=200)
