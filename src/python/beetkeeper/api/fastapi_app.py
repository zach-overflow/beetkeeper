"""
This module should only contain the `FastAPI` app instantiation, along with any sub-APIRouter inclusions.
`beetkeeper.main:cli` (`beatkeeper run` CLI command) imports the app and starts a webserver with it.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from beetkeeper.api.api_routes import api_router
from beetkeeper.api.constants import STATIC_DIRPATH
from beetkeeper.api.ui_routes import ui_router
from beetkeeper.core import ImportStore, ImportWorker
from beetkeeper.db.session import make_engine, make_sessionmaker
from beetkeeper.settings import CONFIG_PATH_ENVVAR, load_config

_LOGGER = logging.getLogger(__name__)
# Package-anchored demo beets config (NOT cwd-relative): beetkeeper/api/ -> beetkeeper/settings/. Resolved
# at import time so the async lifespan does no blocking pathlib I/O. It carries a `beetkeeper` section.
_DEMO_CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings" / "demo_beets_config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initializes app-lifetime state (DB engine + session-maker) from the configured `UserConfig`.

    The config path (the beets config, whose optional `beetkeeper` section holds beetkeeper's settings) is
    read from the `BEETKEEPER_CONFIG` env var (set by `beetkeeper run`). If it is absent the demo beets
    config is used and a warning is logged, so the app still boots for cases that do not touch the database
    (e.g. importing the app in tests). Endpoints using `get_session` will fail until started with a config.
    """
    conf_env = os.environ.get(CONFIG_PATH_ENVVAR)
    if conf_env:
        conf_path = Path(conf_env)
    else:
        conf_path = _DEMO_CONFIG_PATH
        _LOGGER.warning("`%s` is not set; using the demo beets config at %s.", CONFIG_PATH_ENVVAR, conf_path)
    user_config = load_config(conf_path)
    app.state.user_config = user_config
    engine = make_engine(user_config.database.async_url)
    app.state.db_engine = engine
    sessionmaker = make_sessionmaker(engine)
    app.state.db_sessionmaker = sessionmaker

    # Import state lives in the DB (shared across processes); each process runs the import worker, but only
    # the lease holder runs imports. `run()` serves a `BlockingPortal` for beets' pipeline threads.
    worker = ImportWorker(user_config.beets_config_filepath, ImportStore(sessionmaker))
    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(worker.run)
            yield
            # Shutdown: cancel the worker's scope here (after `yield`) so the task group absorbs the
            # cancellation; engine disposal happens in the outer `finally`, outside the cancelled scope.
            # NOTE: a non-abandoning `to_thread` import in flight delays shutdown until it finishes;
            # cancelling requests stop but does not kill the beets pipeline (cooperative abort only).
            task_group.cancel_scope.cancel()
    finally:
        await engine.dispose()


beetkeeper_app = FastAPI(title="beetkeeper", lifespan=lifespan)
# Templates resolve asset URLs via `url_for('static', ...)` against this mount name, so the prefix here is
# the single source of truth for static URLs (see `base_template.html`).
beetkeeper_app.mount("/static", StaticFiles(directory=STATIC_DIRPATH), name="static")
beetkeeper_app.include_router(api_router)
beetkeeper_app.include_router(ui_router)
