"""
This module should only contain the `FastAPI` app instantiation, along with any sub-APIRouter inclusions.
`beetkeeper.main:cli` (`beatkeeper run` CLI command) imports the app and starts a webserver with it.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from beetkeeper.api.api_routes import api_router
from beetkeeper.api.constants import STATIC_DIRPATH


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Configures one-time setup of any immutable application state singletons during initial application startup."""
    # TODO[Claude]: `beets_config` is initialized to an empty dict with no source. Populate it (or replace
    #     it) once the beets-integration model is decided (see `beetkeeper.core.beet_commands`). Source the
    #     beets config/library location from `UserConfig`. Also init any DB engine/session-maker here.
    app.state.beets_config = dict()
    yield
    # Any teardown logic on app shutdown would run here (possibly in a `finally` block, depending on the logic).


beetkeeper_app = FastAPI(title="beetkeeper", lifespan=lifespan)
# Templates resolve asset URLs via `url_for('static', ...)` against this mount name, so the prefix here is
# the single source of truth for static URLs (see `base_template.html`).
beetkeeper_app.mount("/static", StaticFiles(directory=STATIC_DIRPATH), name="static")
# TODO[Claude]: only the RESTful `api_router` is mounted. The HTML-serving `ui_router` aggregator now
#     exists at `beetkeeper.api.ui_routes.ui_router` (prefix `/ui`) but is never included here — add
#     `beetkeeper_app.include_router(ui_router)`. (Note its `__init__` currently has a broken import path
#     that must be fixed first; see the TODO there.)
beetkeeper_app.include_router(api_router)
