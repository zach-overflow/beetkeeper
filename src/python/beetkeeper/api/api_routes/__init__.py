"""
Aggregates the JSON `APIRouter`s (grouped per functional domain) under the `/api` prefix.

The HTML-serving `ui_routes` router is aggregated separately and mounted (not under `/api`) in
`beetkeeper.api.fastapi_app`.
"""

from fastapi import APIRouter

from beetkeeper.api.api_routes.events_router import events_router
from beetkeeper.api.api_routes.health_router import health_router
from beetkeeper.api.api_routes.import_router import import_router
from beetkeeper.api.api_routes.query_router import query_router

api_router = APIRouter(prefix="/api", include_in_schema=True)
api_router.include_router(events_router)
api_router.include_router(health_router)
api_router.include_router(import_router)
api_router.include_router(query_router)

__all__ = ["api_router"]
