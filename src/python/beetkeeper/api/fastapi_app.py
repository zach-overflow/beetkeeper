from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from beetkeeper.api.constants import STATIC_DIRPATH
from beetkeeper.api.routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Configures one-time setup of any immutable application state singletons during initial application startup."""
    app.state.beets_config = dict()
    yield
    # Any teardown logic on app shutdown should run here.


# def custom_generate_unique_id(route: APIRoute) -> str:
#     return f"{route.tags[0]}-{route.name}"

beetkeeper_app = FastAPI(title="beetkeeper", lifespan=lifespan)
beetkeeper_app.mount("/static", StaticFiles(directory=STATIC_DIRPATH), name="static")
beetkeeper_app.include_router(api_router)
