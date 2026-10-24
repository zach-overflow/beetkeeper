"""Lifecycle tests for `ImportWorker.run()` under the single-worker model (run against a migrated temp DB).

These cover the restart/crash failure modes: a freshly-started worker takes over a dead process's expired
lease and fails its orphaned jobs (retrying recovery after a transient error), a live (unexpired) lease is
respected, a failed import or failed post-import bookkeeping doesn't kill the worker loop, terminal-status
writes are retried, aborted jobs land on ABORTED, and the `DecisionBridge` resolves both the answered and
the aborted decision waits. The beets pipeline itself is mocked out (`_run_import_blocking`); no real
import, library, or network is touched.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

import anyio
import pytest
from pytest_mock import MockerFixture
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.core import ImportAction, ImportDecision, ImportJobStatus, ImportStore, ImportWorker
from beetkeeper.core.import_jobs import DecisionRequest
from beetkeeper.core.import_worker import DecisionBridge
from beetkeeper.db.models import ListenerEvent

_DEAD_WORKER_ID = "deadhost:999:deadbeef"
_POLL = 0.02
_WAIT_TIMEOUT = 10.0


@pytest.fixture
def worker(import_store: ImportStore, tmp_path: Path) -> ImportWorker:
    """A worker over the temp-DB store; the beets config path is never opened (imports are mocked)."""
    return ImportWorker(tmp_path / "unused-beets-config.yaml", import_store)


@pytest.fixture
def fast_polls(mocker: MockerFixture) -> None:
    """Shrink the worker's poll/renew/retry cadences so lifecycle tests converge in milliseconds."""
    for name in (
        "_IDLE_POLL",
        "_RENEW_INTERVAL",
        "_OUTPUT_FLUSH_INTERVAL",
        "_DECISION_POLL",
        "_FINALIZE_RETRY_INTERVAL",
    ):
        mocker.patch(f"beetkeeper.core.import_worker.{name}", _POLL)


async def _wait_until(condition: Callable[[], Awaitable[bool]]) -> None:
    """Poll `condition` until it holds (fails the test after `_WAIT_TIMEOUT`)."""
    with anyio.fail_after(_WAIT_TIMEOUT):
        while not await condition():
            await anyio.sleep(_POLL)


async def _run_worker_until(worker: ImportWorker, condition: Callable[[], Awaitable[bool]]) -> None:
    """Run `worker.run()` in the background until `condition()` holds, then cancel it.

    Cancellation can land while an aiosqlite query is in flight; the store's shielded sessions and
    `run()`'s own guard are expected to absorb that and exit cleanly.
    """
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(worker.run)
        await _wait_until(condition)
        task_group.cancel_scope.cancel()


def _job_status_condition(store: ImportStore, job_id: str, status: ImportJobStatus) -> Callable[[], Awaitable[bool]]:
    async def _check() -> bool:
        view = await store.get(job_id)
        return view is not None and view.status is status

    return _check


async def _seed_dead_leader(store: ImportStore, *, lease_seconds: float = -1) -> str:
    """Simulate another leader process: a RUNNING job it claimed plus its lease (already expired by default)."""
    job = await store.create(["/music/orphan"])
    claimed = await store.claim_next(_DEAD_WORKER_ID)
    assert claimed is not None and claimed.id == job.id
    await store.ensure_lock_row()
    assert await store.acquire_lock(_DEAD_WORKER_ID, lease_seconds=lease_seconds) is True
    return job.id


def _fail_first_call_then_delegate(
    mocker: MockerFixture, store: ImportStore, method_name: str, error: Exception
) -> list[int]:
    """Patch `store.<method_name>` to raise `error` on the first call and delegate afterwards.

    Returns the (mutable) call-counting list so tests can assert the retry actually happened.
    """
    real_method = getattr(store, method_name)
    calls: list[int] = []

    async def _flaky(*args: object, **kwargs: object) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise error
        return await real_method(*args, **kwargs)

    mocker.patch.object(store, method_name, side_effect=_flaky)
    return calls


def _locked_error(statement: str) -> OperationalError:
    return OperationalError(statement, {}, Exception("database is locked"))


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_restart_takes_over_expired_lease_and_fails_orphaned_job(
    import_store: ImportStore, worker: ImportWorker
) -> None:
    """After a crash/unclean shutdown, the next startup fails the job the dead process left RUNNING."""
    job_id = await _seed_dead_leader(import_store)

    await _run_worker_until(worker, _job_status_condition(import_store, job_id, ImportJobStatus.FAILED))

    view = await import_store.get(job_id)
    assert view is not None and view.error is not None and "restarted" in view.error
    assert await import_store.lock_holder() == worker._worker_id


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_orphan_recovery_is_retried_after_a_transient_error(
    import_store: ImportStore, worker: ImportWorker, mocker: MockerFixture
) -> None:
    """A transient DB error during first-election orphan recovery doesn't skip recovery for good."""
    job_id = await _seed_dead_leader(import_store)
    calls = _fail_first_call_then_delegate(mocker, import_store, "recover_orphans", _locked_error("UPDATE ..."))

    await _run_worker_until(worker, _job_status_condition(import_store, job_id, ImportJobStatus.FAILED))

    assert len(calls) >= 2  # first attempt raised; a later cycle re-ran recovery


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_orphan_recovery_spares_jobs_claimed_by_this_worker(
    import_store: ImportStore, worker: ImportWorker
) -> None:
    """Becoming leader only fails *other* workers' active jobs, never one this worker id already claimed."""
    job = await import_store.create(["/music/mine"])
    claimed = await import_store.claim_next(worker._worker_id)
    assert claimed is not None and claimed.id == job.id

    async def _worker_is_leader() -> bool:
        return await import_store.lock_holder() == worker._worker_id

    await _run_worker_until(worker, _worker_is_leader)
    for _ in range(5):  # let a few leader loop iterations pass before checking
        await anyio.sleep(_POLL)
    view = await import_store.get(job.id)
    assert view is not None and view.status is ImportJobStatus.RUNNING


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_worker_respects_a_live_lease_and_recovers_nothing(
    import_store: ImportStore, worker: ImportWorker
) -> None:
    """While another holder's lease is unexpired, the worker stays a non-leader and touches no jobs."""
    job_id = await _seed_dead_leader(import_store, lease_seconds=60)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(worker.run)
        await anyio.sleep(_POLL * 15)  # many acquire attempts, all of which must lose
        task_group.cancel_scope.cancel()

    assert await import_store.lock_holder() == _DEAD_WORKER_ID
    view = await import_store.get(job_id)
    assert view is not None and view.status is ImportJobStatus.RUNNING


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_completed_job_persists_output_without_recording_events(
    import_store: ImportStore,
    worker: ImportWorker,
    session_factory: async_sessionmaker[AsyncSession],
    mocker: MockerFixture,
) -> None:
    """The claim -> run -> COMPLETED path persists the terminal status and output — and never writes
    `ListenerEvent` rows: recorded events originate exclusively from the beetkeeper plugin's POSTs."""
    mocker.patch.object(ImportWorker, "_run_import_blocking", return_value=None)
    job = await import_store.create(["/music/a"])

    await _run_worker_until(worker, _job_status_condition(import_store, job.id, ImportJobStatus.COMPLETED))

    view = await import_store.get(job.id)
    assert view is not None and view.output is not None and "Import completed." in view.output
    async with session_factory() as session:
        assert (await session.execute(select(ListenerEvent))).scalars().all() == []


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_failed_import_marks_job_failed_and_worker_survives(
    import_store: ImportStore, worker: ImportWorker, mocker: MockerFixture
) -> None:
    """An import that raises fails ONLY that job — the worker loop stays alive and runs the next one."""
    mocker.patch.object(ImportWorker, "_run_import_blocking", side_effect=[RuntimeError("beets exploded"), None])
    first = await import_store.create(["/music/bad"])
    second = await import_store.create(["/music/good"])

    await _run_worker_until(worker, _job_status_condition(import_store, second.id, ImportJobStatus.COMPLETED))

    failed = await import_store.get(first.id)
    assert failed is not None and failed.status is ImportJobStatus.FAILED
    assert failed.error is not None and "beets exploded" in failed.error
    assert failed.output is not None and "Import failed: beets exploded" in failed.output


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_bookkeeping_failure_fails_the_job_and_worker_survives(
    import_store: ImportStore, worker: ImportWorker, mocker: MockerFixture
) -> None:
    """A non-OperationalError from post-import bookkeeping lands on the job, not the worker loop."""
    mocker.patch.object(ImportWorker, "_run_import_blocking", return_value=None)
    error = IntegrityError("SELECT ...", {}, Exception("malformed database schema"))
    calls = _fail_first_call_then_delegate(mocker, import_store, "is_abort_requested", error)
    first = await import_store.create(["/music/bad-bookkeeping"])
    second = await import_store.create(["/music/good"])

    await _run_worker_until(worker, _job_status_condition(import_store, second.id, ImportJobStatus.COMPLETED))

    failed = await import_store.get(first.id)
    assert failed is not None and failed.status is ImportJobStatus.FAILED
    assert failed.error is not None and "malformed database schema" in failed.error
    assert len(calls) >= 2  # the second job's abort check still went through via the delegate


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_transient_terminal_write_failure_is_retried(
    import_store: ImportStore, worker: ImportWorker, mocker: MockerFixture
) -> None:
    """A transient error during the terminal status write is retried, not swallowed into a zombie job."""
    mocker.patch.object(ImportWorker, "_run_import_blocking", return_value=None)
    calls = _fail_first_call_then_delegate(mocker, import_store, "set_status", _locked_error("UPDATE ..."))
    job = await import_store.create(["/music/a"])

    await _run_worker_until(worker, _job_status_condition(import_store, job.id, ImportJobStatus.COMPLETED))

    assert len(calls) >= 2  # first terminal write raised; the retry landed COMPLETED


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_transient_db_error_does_not_kill_the_worker(
    import_store: ImportStore, worker: ImportWorker, mocker: MockerFixture
) -> None:
    """A transient `OperationalError` (e.g. SQLite "database is locked") is retried, not worker-fatal."""
    calls = _fail_first_call_then_delegate(mocker, import_store, "claim_next", _locked_error("SELECT ..."))
    mocker.patch.object(ImportWorker, "_run_import_blocking", return_value=None)
    job = await import_store.create(["/music/a"])

    await _run_worker_until(worker, _job_status_condition(import_store, job.id, ImportJobStatus.COMPLETED))

    assert len(calls) >= 2  # the first attempt raised; the worker survived and re-claimed


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
async def test_aborted_job_ends_aborted_without_recording_events(
    import_store: ImportStore,
    worker: ImportWorker,
    session_factory: async_sessionmaker[AsyncSession],
    mocker: MockerFixture,
) -> None:
    """A job aborted mid-run lands on ABORTED and its (partial) import is not recorded as events."""
    mocker.patch.object(ImportWorker, "_run_import_blocking", return_value=None)
    job = await import_store.create(["/music/a"])
    assert await import_store.request_abort(job.id) is True

    await _run_worker_until(worker, _job_status_condition(import_store, job.id, ImportJobStatus.ABORTED))

    view = await import_store.get(job.id)
    assert view is not None and view.output is not None and "Import aborted." in view.output
    async with session_factory() as session:
        assert (await session.execute(select(ListenerEvent))).scalars().all() == []


async def _submit_asis_decision(store: ImportStore, job_id: str) -> bool:
    return await store.submit_decision(job_id, ImportDecision(action=ImportAction.ASIS))


async def _request_abort(store: ImportStore, job_id: str) -> bool:
    return await store.request_abort(job_id)


@pytest.mark.anyio
@pytest.mark.usefixtures("fast_polls")
@pytest.mark.parametrize(
    ("unblock", "expected_action"),
    [(_submit_asis_decision, ImportAction.ASIS), (_request_abort, ImportAction.SKIP)],
    ids=["submitted-decision", "abort-requested"],
)
async def test_decision_bridge_unblocks_the_waiting_import(
    import_store: ImportStore, unblock: Callable[[ImportStore, str], Awaitable[bool]], expected_action: ImportAction
) -> None:
    """The bridge parks the job on AWAITING_DECISION and unblocks on a submitted decision or an abort."""
    job = await import_store.create(["/music/a"])
    await import_store.claim_next("worker-1")
    bridge = DecisionBridge(import_store)
    delivered: list[ImportDecision] = []

    async def _request() -> None:
        delivered.append(await bridge.request(DecisionRequest(job_id=job.id, task_id="t1", prompt="pick")))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(_request)
        await _wait_until(_job_status_condition(import_store, job.id, ImportJobStatus.AWAITING_DECISION))
        assert await unblock(import_store, job.id) is True

    assert len(delivered) == 1 and delivered[0].action is expected_action
    if expected_action is ImportAction.ASIS:  # a consumed decision flips the job back to RUNNING
        resumed = await import_store.get(job.id)
        assert resumed is not None and resumed.status is ImportJobStatus.RUNNING
