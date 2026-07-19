"""
Database-backed, cross-process store for interactive import jobs.

Replaces the old in-memory registry so import state is shared across uvicorn workers and survives restarts.
The store is the single source of truth; the leader-elected `ImportWorker` runs the actual beets import,
while any worker process serves submit/status/decision/abort by reading and writing these rows.

Coordination primitives (all SQLite-atomic):
  * `acquire_lock` — a leased, single-row lock (`import_lock`) electing the one process that runs imports.
  * `claim_next`   — the leader flips one PENDING job to RUNNING.
  * `submit_decision` / `take_decision` — the UI writes a decision row; the leader polls and consumes it.
  * `request_abort` / `is_abort_requested` — cooperative cancellation flag.
  * `recover_orphans` — a freshly-elected leader fails jobs left active by a dead leader.

All timestamps are stored naive-UTC (the SQLite DATETIME column is tz-naive); compare naive against naive.
Query expressions use `sqlmodel.col(...)` so the SQLModel columns type-check as SQLAlchemy column elements.
"""

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from beetkeeper.core.import_jobs import DecisionRequest, ImportDecision, ImportJob, ImportJobStatus
from beetkeeper.db.models import ImportJobRecord, ImportLock
from beetkeeper.db.session import shielded_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_LOGGER = logging.getLogger(__name__)
_LOCK_ID = 1
_ACTIVE = [ImportJobStatus.RUNNING.value, ImportJobStatus.AWAITING_DECISION.value]
_ABORTABLE = [ImportJobStatus.PENDING.value, *_ACTIVE]


def _utcnow() -> datetime:
    """Naive UTC 'now' matching the tz-naive SQLite DATETIME columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _rowcount(result: Any) -> int:
    """Affected-row count of a DML result (the runtime `CursorResult` exposes `rowcount`)."""
    return int(result.rowcount)


class ImportStore:
    """Async, DB-backed store for import jobs + the import-worker leader lock."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        """Bind the store to the app's async sessionmaker (the shared beetkeeper DB)."""
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """A store session shielded from task cancellation (see `db.session.shielded_session`).

        The worker (and its renew/flush subtasks) are cancelled at shutdown; store operations are tiny,
        so they run to completion under the shield and cancellation is delivered at the caller's next
        checkpoint instead of mid-query.
        """
        async with shielded_session(self._sessionmaker) as session:
            yield session

    @staticmethod
    def _to_view(record: ImportJobRecord) -> ImportJob:
        pending = (
            DecisionRequest.model_validate_json(record.pending_decision_json) if record.pending_decision_json else None
        )
        return ImportJob(
            id=record.id,
            status=ImportJobStatus(record.status),
            paths=json.loads(record.paths_json),
            created_at=record.created_at,
            error=record.error,
            pending_decision=pending,
            decision_submitted=record.submitted_decision_json is not None,
            output=record.output,
            quiet=record.quiet,
            logpath=record.logpath,
            group_albums=record.group_albums,
            flat=record.flat,
            set_fields=json.loads(record.set_fields_json) if record.set_fields_json else {},
        )

    async def create(
        self,
        paths: Sequence[str],
        *,
        quiet: bool = False,
        logpath: str | None = None,
        group_albums: bool = False,
        flat: bool = False,
        set_fields: Mapping[str, str] | None = None,
    ) -> ImportJob:
        """Insert a new PENDING job and return its view.

        The keyword arguments are the per-job import settings, mirroring `beet import` flags: `quiet` runs
        non-interactively (`-q`), plus `logpath` (`-l`), `group_albums`, `flat`, and `set_fields` (`--set`).
        Each job keeps the values it was submitted with, so concurrent/ad-hoc imports can differ.
        """
        _LOGGER.debug("Creating ImportJob ...")
        now = _utcnow()
        record = ImportJobRecord(
            id=uuid4().hex,
            status=ImportJobStatus.PENDING.value,
            paths_json=json.dumps(list(paths)),
            created_at=now,
            updated_at=now,
            quiet=quiet,
            logpath=logpath,
            group_albums=group_albums,
            flat=flat,
            set_fields_json=json.dumps(dict(set_fields)) if set_fields else None,
        )
        async with self._session() as session:
            session.add(record)
            await session.commit()
        _LOGGER.debug("ImportJob created")
        return self._to_view(record)

    async def get(self, job_id: str) -> ImportJob | None:
        """Return the job view for `job_id`, or None."""
        async with self._session() as session:
            record = await session.get(ImportJobRecord, job_id)
            return self._to_view(record) if record is not None else None

    async def list(self) -> list[ImportJob]:
        """Return all jobs, oldest first."""
        async with self._session() as session:
            records = (
                (await session.execute(select(ImportJobRecord).order_by(col(ImportJobRecord.created_at))))
                .scalars()
                .all()
            )
            return [self._to_view(record) for record in records]

    async def set_status(self, job_id: str, status: ImportJobStatus, *, error: str | None = None) -> None:
        """Set a job's status (and optional error); clears any pending decision."""
        values: dict[str, object] = {"status": status.value, "pending_decision_json": None, "updated_at": _utcnow()}
        if error is not None:
            values["error"] = error
        async with self._session() as session:
            await session.execute(update(ImportJobRecord).where(col(ImportJobRecord.id) == job_id).values(**values))
            await session.commit()

    async def set_output(self, job_id: str, output: str) -> None:
        """Persist the import job's accumulated output text (the leader flushes this as the import runs)."""
        async with self._session() as session:
            await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.id) == job_id)
                .values(output=output, updated_at=_utcnow())
            )
            await session.commit()

    async def set_awaiting(self, request: DecisionRequest) -> None:
        """Park a job on a decision: store the request and mark AWAITING_DECISION (clears any stale answer)."""
        async with self._session() as session:
            await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.id) == request.job_id)
                .values(
                    status=ImportJobStatus.AWAITING_DECISION.value,
                    pending_decision_json=request.model_dump_json(),
                    submitted_decision_json=None,
                    updated_at=_utcnow(),
                )
            )
            await session.commit()

    async def submit_decision(self, job_id: str, decision: ImportDecision) -> bool:
        """Record the UI's decision; True only if the job was awaiting one and none was already submitted."""
        async with self._session() as session:
            result = await session.execute(
                update(ImportJobRecord)
                .where(
                    col(ImportJobRecord.id) == job_id,
                    col(ImportJobRecord.status) == ImportJobStatus.AWAITING_DECISION.value,
                    col(ImportJobRecord.submitted_decision_json).is_(None),
                )
                .values(submitted_decision_json=decision.model_dump_json(), updated_at=_utcnow())
            )
            await session.commit()
            return _rowcount(result) == 1

    async def take_decision(self, job_id: str) -> ImportDecision | None:
        """Leader-side: atomically consume a submitted decision (clears it and flips back to RUNNING)."""
        async with self._session() as session:
            record = await session.get(ImportJobRecord, job_id)
            if record is None or record.submitted_decision_json is None:
                return None
            decision = ImportDecision.model_validate_json(record.submitted_decision_json)
            result = await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.id) == job_id, col(ImportJobRecord.submitted_decision_json).is_not(None))
                .values(
                    submitted_decision_json=None,
                    pending_decision_json=None,
                    status=ImportJobStatus.RUNNING.value,
                    updated_at=_utcnow(),
                )
            )
            await session.commit()
            return decision if _rowcount(result) == 1 else None

    async def request_abort(self, job_id: str) -> bool:
        """Flag a non-terminal job for cooperative abort; True if such a job exists."""
        async with self._session() as session:
            result = await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.id) == job_id, col(ImportJobRecord.status).in_(_ABORTABLE))
                .values(abort_requested=True, updated_at=_utcnow())
            )
            await session.commit()
            return _rowcount(result) == 1

    async def is_abort_requested(self, job_id: str) -> bool:
        """Whether abort has been requested for `job_id`."""
        async with self._session() as session:
            record = await session.get(ImportJobRecord, job_id)
            return bool(record and record.abort_requested)

    async def ensure_lock_row(self) -> None:
        """Create the singleton lock row if it doesn't exist yet (idempotent)."""
        async with self._session() as session:
            if await session.get(ImportLock, _LOCK_ID) is not None:
                return
            session.add(ImportLock(id=_LOCK_ID))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()  # another process inserted it first

    async def acquire_lock(self, worker_id: str, lease_seconds: float) -> bool:
        """Acquire or renew the import-worker lease via one atomic conditional UPDATE; True if held."""
        now = _utcnow()
        async with self._session() as session:
            result = await session.execute(
                update(ImportLock)
                .where(
                    col(ImportLock.id) == _LOCK_ID,
                    (col(ImportLock.holder) == worker_id)
                    | (col(ImportLock.holder).is_(None))
                    | (col(ImportLock.lease_expires_at) < now),
                )
                .values(holder=worker_id, lease_expires_at=now + timedelta(seconds=lease_seconds))
            )
            await session.commit()
            return _rowcount(result) == 1

    async def lock_holder(self) -> str | None:
        """The worker id currently holding the import lease (the elected import leader), or None."""
        async with self._session() as session:
            lock = await session.get(ImportLock, _LOCK_ID)
            return lock.holder if lock is not None else None

    async def release_lock(self, worker_id: str) -> None:
        """Release the lease if we hold it (best-effort, on shutdown)."""
        async with self._session() as session:
            await session.execute(
                update(ImportLock)
                .where(col(ImportLock.id) == _LOCK_ID, col(ImportLock.holder) == worker_id)
                .values(holder=None, lease_expires_at=None)
            )
            await session.commit()

    async def claim_next(self, worker_id: str) -> ImportJob | None:
        """Leader-side: flip the oldest PENDING job to RUNNING under `worker_id`, or None if there are none."""
        async with self._session() as session:
            record = (
                (
                    await session.execute(
                        select(ImportJobRecord)
                        .where(col(ImportJobRecord.status) == ImportJobStatus.PENDING.value)
                        .order_by(col(ImportJobRecord.created_at))
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if record is None:
                return None
            result = await session.execute(
                update(ImportJobRecord)
                .where(
                    col(ImportJobRecord.id) == record.id, col(ImportJobRecord.status) == ImportJobStatus.PENDING.value
                )
                .values(status=ImportJobStatus.RUNNING.value, claimed_by=worker_id, updated_at=_utcnow())
            )
            await session.commit()
            if _rowcount(result) != 1:
                return None
        return await self.get(record.id)

    async def recover_orphans(self, worker_id: str) -> int:
        """Fail any active job NOT claimed by us (left behind by a dead leader); returns how many."""
        async with self._session() as session:
            result = await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.status).in_(_ACTIVE), col(ImportJobRecord.claimed_by) != worker_id)
                .values(
                    status=ImportJobStatus.FAILED.value,
                    error="Interrupted: the import worker restarted.",
                    pending_decision_json=None,
                    updated_at=_utcnow(),
                )
            )
            await session.commit()
            return _rowcount(result)
