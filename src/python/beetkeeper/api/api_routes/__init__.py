"""
This module should containg files defining various `APIRouter` instances, grouped per file based on their
functional domain. There may need to be additional routers, and all the route functions for them are currently
useless placeholders.

TODO[Claude]: the placeholder routes are copy-paste noise that should not be pattern-matched: every router
    defines a function literally named `foo`, and both `config_router` and `query_router` expose
    `POST /login/access-token` (nonsensical outside an auth router). Replace per functional domain.
TODO[Claude]: this aggregator wires up only RESTful routers under `/api`. The HTML-serving `ui_routes`
    router(s) are not aggregated or mounted anywhere — add a `ui_router` and include it from
    `beetkeeper.api.fastapi_app` (not under `/api`).
"""

from fastapi import APIRouter

from beetkeeper.api.api_routes.config_router import config_router
from beetkeeper.api.api_routes.events_router import events_router
from beetkeeper.api.api_routes.files_router import files_router
from beetkeeper.api.api_routes.import_router import import_router
from beetkeeper.api.api_routes.query_router import query_router

api_router = APIRouter(prefix="/api")
api_router.include_router(config_router)
api_router.include_router(events_router)
api_router.include_router(files_router)
api_router.include_router(import_router)
api_router.include_router(query_router)

__all__ = ["api_router"]
