"""
Database-backed, cross-process store for interactive import jobs.

Import state lives in the database so it survives restarts and is visible to every process sharing it. The
store is the single source of truth; the leader-elected `ImportWorker` runs the actual beets import, while
any process serves submit/status/decision/abort by reading and writing these rows. Every coordination
primitive (lock lease, job claim, decision hand-off, abort flag, orphan recovery) is one SQLite-atomic
statement.

All timestamps are stored naive-UTC (the SQLite DATETIME column is tz-naive); compare naive against naive.
Query expressions use `sqlmodel.col(...)` so the SQLModel columns type-check as SQLAlchemy column elements.
"""

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from beetkeeper.core.import_jobs import CleanSlateSubject, DecisionRequest, ImportDecision, ImportJob, ImportJobStatus
from beetkeeper.db.models import ImportJobRecord, ImportLock, InferredSourcePath, naive_utcnow
from beetkeeper.db.session import affected_rows, shielded_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_LOGGER = logging.getLogger(__name__)
_LOCK_ID = 1
_ACTIVE = [ImportJobStatus.RUNNING.value, ImportJobStatus.AWAITING_DECISION.value]
_ABORTABLE = [ImportJobStatus.PENDING.value, *_ACTIVE]


class ImportStore:
    """Async, DB-backed store for import jobs + the import-worker leader lock."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        """Bind the store to the app's async sessionmaker (the shared beetkeeper DB)."""
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """
        A store session shielded from task cancellation (see `db.session.shielded_session`).

        The worker (and its renew/flush subtasks) are cancelled at shutdown; store operations are tiny,
        so they run to completion under the shield and cancellation is delivered at the caller's next
        checkpoint instead of mid-query.
        """
        async with shielded_session(self._sessionmaker) as session:
            yield session

    @staticmethod
    def _to_view(record: ImportJobRecord) -> ImportJob:
        """Map a persisted row onto the API-facing `ImportJob` view (decoding its JSON columns)."""
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
            clean_slate_album_id=record.clean_slate_album_id,
            clean_slate_item_id=record.clean_slate_item_id,
            clean_slate_allow_fewer_files=record.clean_slate_allow_fewer_files,
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
        clean_slate_album_id: int | None = None,
        clean_slate_item_id: int | None = None,
        clean_slate_allow_fewer_files: bool = False,
    ) -> ImportJob:
        """
        Insert a new PENDING job and return its view.

        The keyword arguments are the per-job import settings, mirroring `beet import` flags: `quiet` runs
        non-interactively (`-q`), plus `logpath` (`-l`), `group_albums`, `flat`, and `set_fields` (`--set`).
        Each job keeps the values it was submitted with, so concurrent/ad-hoc imports can differ.

        `clean_slate_album_id` / `clean_slate_item_id` (at most one) name the library entry the worker removes
        before importing `paths` — its raw source folder — afresh (see `core.clean_slate`);
        `clean_slate_allow_fewer_files` records the submitter's opt-in to a source with fewer files.
        """
        if clean_slate_album_id is not None and clean_slate_item_id is not None:
            raise ValueError("A clean slate names an album or a standalone track, not both.")
        _LOGGER.debug("Creating ImportJob ...")
        now = naive_utcnow()
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
            clean_slate_album_id=clean_slate_album_id,
            clean_slate_item_id=clean_slate_item_id,
            clean_slate_allow_fewer_files=clean_slate_allow_fewer_files,
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
        values: dict[str, object] = {
            "status": status.value,
            "pending_decision_json": None,
            "updated_at": naive_utcnow(),
        }
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
                .values(output=output, updated_at=naive_utcnow())
            )
            await session.commit()

    async def retarget_inferred_source_paths(
        self, subject: CleanSlateSubject, old_id: int, new_id: int | None, old_item_ids: Sequence[int]
    ) -> None:
        """
        Move a clean-slated entry's inferred source path onto the id its fresh import got, or drop it.

        beets re-numbers rows on every import, so after a clean slate the inference stored under the old id
        would dangle (or, since beets reuses freed ids, attach to an unrelated entry later). When the import
        produced exactly one new entry (`new_id`) the inference moves with it — the folder it names is what
        was just imported — otherwise it is deleted. Inferences for the removed album's tracks are dropped.
        """
        stale_track_ids = set(old_item_ids) - ({old_id} if subject == "track" else set())
        async with self._session() as session:
            if stale_track_ids:
                await session.execute(
                    delete(InferredSourcePath).where(
                        col(InferredSourcePath.subject_type) == "track",
                        col(InferredSourcePath.beets_id).in_(stale_track_ids),
                    )
                )
            row = (
                await session.execute(
                    select(InferredSourcePath).where(
                        col(InferredSourcePath.subject_type) == subject, col(InferredSourcePath.beets_id) == old_id
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                if new_id is None:
                    await session.delete(row)
                elif new_id != old_id:
                    await session.execute(
                        delete(InferredSourcePath).where(
                            col(InferredSourcePath.subject_type) == subject, col(InferredSourcePath.beets_id) == new_id
                        )
                    )
                    row.beets_id = new_id
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
                    updated_at=naive_utcnow(),
                )
            )
            await session.commit()

    async def submit_decision(self, job_id: str, decision: ImportDecision) -> bool:
        """
        Record the UI's decision; True only if the job was awaiting one and none was already submitted.

        The leader polls for the row with `take_decision`, which consumes it.
        """
        async with self._session() as session:
            result = await session.execute(
                update(ImportJobRecord)
                .where(
                    col(ImportJobRecord.id) == job_id,
                    col(ImportJobRecord.status) == ImportJobStatus.AWAITING_DECISION.value,
                    col(ImportJobRecord.submitted_decision_json).is_(None),
                )
                .values(submitted_decision_json=decision.model_dump_json(), updated_at=naive_utcnow())
            )
            await session.commit()
            return affected_rows(result) == 1

    async def take_decision(self, job_id: str) -> ImportDecision | None:
        """
        Leader-side: atomically consume a decision the UI wrote via `submit_decision`.

        Clears the pending and submitted decision columns and flips the job back to RUNNING; None when no
        decision has been submitted (or another consumer got there first).
        """
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
                    updated_at=naive_utcnow(),
                )
            )
            await session.commit()
            return decision if affected_rows(result) == 1 else None

    async def request_abort(self, job_id: str) -> bool:
        """Flag a non-terminal job for cooperative abort (the worker polls `is_abort_requested`); True if one exists."""
        async with self._session() as session:
            result = await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.id) == job_id, col(ImportJobRecord.status).in_(_ABORTABLE))
                .values(abort_requested=True, updated_at=naive_utcnow())
            )
            await session.commit()
            return affected_rows(result) == 1

    async def is_abort_requested(self, job_id: str) -> bool:
        """Whether a cooperative abort has been requested for `job_id` (see `request_abort`)."""
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
        """
        Acquire or renew the import-worker lease via one atomic conditional UPDATE; True if held.

        The lease is the single `import_lock` row: whoever holds it is the one process that runs imports, and
        a lease left to expire lets another process take over.
        """
        now = naive_utcnow()
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
            return affected_rows(result) == 1

    async def lock_holder(self) -> str | None:
        """The worker id currently holding the import lease (the elected import leader), or None."""
        async with self._session() as session:
            lock = await session.get(ImportLock, _LOCK_ID)
            return lock.holder if lock is not None else None

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
                .values(status=ImportJobStatus.RUNNING.value, claimed_by=worker_id, updated_at=naive_utcnow())
            )
            await session.commit()
            if affected_rows(result) != 1:
                return None
        return await self.get(record.id)

    async def recover_orphans(self, worker_id: str) -> int:
        """
        Fail any active job not claimed by `worker_id` (left behind by a dead leader); returns how many.

        A freshly elected leader runs this before claiming new work.
        """
        async with self._session() as session:
            result = await session.execute(
                update(ImportJobRecord)
                .where(col(ImportJobRecord.status).in_(_ACTIVE), col(ImportJobRecord.claimed_by) != worker_id)
                .values(
                    status=ImportJobStatus.FAILED.value,
                    error="Interrupted: the import worker restarted.",
                    pending_decision_json=None,
                    updated_at=naive_utcnow(),
                )
            )
            await session.commit()
            return affected_rows(result)
