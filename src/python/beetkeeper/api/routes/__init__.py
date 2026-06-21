from fastapi import APIRouter

from beetkeeper.api.routes.config_router import config_router
from beetkeeper.api.routes.files_router import files_router
from beetkeeper.api.routes.import_router import import_router
from beetkeeper.api.routes.query_router import query_router

api_router = APIRouter(prefix="/api")
api_router.include_router(config_router)
api_router.include_router(files_router)
api_router.include_router(import_router)
api_router.include_router(query_router)

__all__ = ["api_router"]
