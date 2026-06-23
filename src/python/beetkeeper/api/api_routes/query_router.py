import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)
query_router = APIRouter(prefix="/query")


# TODO[Claude]: placeholder — `POST /login/access-token` is wrong for a query router (copy-pasted from the
#     auth template) and the function is named `foo`. Replace with real beets-query endpoints.
@query_router.post("/login/access-token")
async def foo(request: Request) -> JSONResponse:
    _LOGGER.info("Replace this endpoint")
    return JSONResponse(content={}, status_code=200)
