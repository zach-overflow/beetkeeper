"""
Core domain logic the API layer calls into. This is the ONLY package that touches beets internals.

Integration model (decided): beetkeeper drives beets **in-process via its Python API**, not via the
`beet` CLI — beetkeeper and beets are co-located, and in-process access is required for the interactive
importer. See `beetkeeper.core.library` for the rationale and concurrency rules.

  * `library`        — async facade for one-shot ops (query / modify / remove / stats).
  * `import_jobs`    — job status/action enums + decision DTOs + the `ImportJob` view (no beets imports).
  * `import_store`   — DB-backed, cross-process job store + the leader lock.
  * `import_worker`  — the leader-elected worker that runs interactive imports.

beets dev docs: https://beets.readthedocs.io/en/v2.12.0/dev/

Wiring: each process runs `ImportWorker.run()` (started in `api.fastapi_app.lifespan`), but only the
lease holder runs imports. Job state lives in the DB (`ImportStore`), so submit/status/decision/abort
work across `server_workers > 1` and survive restarts. The JSON API is `api.api_routes.import_router` and
the HTMX UI is `api.ui_routes.import_ui_fragments_router` (+ the `/import` page); routes use the store via
`api.dependencies.ImportStoreDep`.

Remaining beets-detail TODOs are marked inline (DTO mapping, duplicate resolution, candidate labels).
"""

from beetkeeper.core.import_jobs import (
    DecisionRequest,
    ImportAction,
    ImportCandidate,
    ImportDecision,
    ImportedAlbum,
    ImportedEntities,
    ImportJob,
    ImportJobStatus,
)
from beetkeeper.core.import_store import ImportStore
from beetkeeper.core.import_worker import ImportWorker
from beetkeeper.core.library import BeetsLibrary

__all__ = [
    "BeetsLibrary",
    "DecisionRequest",
    "ImportAction",
    "ImportCandidate",
    "ImportDecision",
    "ImportJob",
    "ImportJobStatus",
    "ImportStore",
    "ImportWorker",
    "ImportedAlbum",
    "ImportedEntities",
]
