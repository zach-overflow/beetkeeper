"""
Health / diagnostics endpoint.

Reports the serving process's pid and the current import-leader (the `import_lock` holder). The server
runs as a single worker process, so the serving pid and the leader normally coincide; the lease fields
remain observable because job state and the lock are DB-backed (and survive restarts).
"""

import logging
import os
import socket

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from beetkeeper.api.constants import RouteTag
from beetkeeper.api.dependencies import ImportStoreDep

_LOGGER = logging.getLogger(__name__)
health_router = APIRouter(prefix="/health", tags=[RouteTag.MONITOR])


class HealthInfo(BaseModel):
    """Per-process health snapshot."""

    model_config = ConfigDict(frozen=True)
    process_pid: int
    hostname: str
    import_lock_holder: str | None
    is_import_leader: bool
    job_count: int


@health_router.get("")
async def health(store: ImportStoreDep) -> HealthInfo:
    """Report this process's pid, the current import leader (lock holder), and the shared job count."""
    pid = os.getpid()
    hostname = socket.gethostname()
    holder = await store.lock_holder()
    jobs = await store.list()
    return HealthInfo(
        process_pid=pid,
        hostname=hostname,
        import_lock_holder=holder,
        # The worker id is "<hostname>:<pid>:<uuid>"; this process is the leader iff it holds the lock.
        is_import_leader=holder is not None and holder.startswith(f"{hostname}:{pid}:"),
        job_count=len(jobs),
    )
