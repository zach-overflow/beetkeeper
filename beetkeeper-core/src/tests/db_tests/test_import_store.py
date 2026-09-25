"""Tests for the cross-process coordination primitives in `ImportStore` (run against a migrated temp DB).

These prove the multi-worker behaviour: a single leased leader, atomic claim, the DB-mediated decision
handoff, cooperative abort, and orphan recovery on leader takeover.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.core import ImportAction, ImportDecision, ImportJobStatus, ImportStore
from beetkeeper.core.import_jobs import DecisionRequest
from beetkeeper.db.models import InferredSourcePath


def _store(session_factory: async_sessionmaker[AsyncSession]) -> ImportStore:
    return ImportStore(session_factory)


@pytest.mark.anyio
async def test_create_get_list(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a", "/music/b"])
    assert job.status is ImportJobStatus.PENDING
    assert job.paths == ["/music/a", "/music/b"]
    assert job.quiet is False

    fetched = await store.get(job.id)
    assert fetched is not None and fetched.id == job.id
    assert len(await store.list()) == 1
    assert await store.get("missing") is None


@pytest.mark.anyio
async def test_source_label_is_path_basename(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/data/raw/Boards of Canada - Inferno [FLAC]"])
    assert job.source_label == "Boards of Canada - Inferno [FLAC]"
    # Trailing slash is handled (basename of an empty leaf would otherwise be "").
    trailing = await store.create(["/data/raw/Some Album/"])
    assert trailing.source_label == "Some Album"


@pytest.mark.anyio
async def test_create_persists_quiet_flag(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"], quiet=True)
    assert job.quiet is True
    # The flag survives a round-trip through the DB (the worker reads it on claim, possibly in another process).
    fetched = await store.get(job.id)
    assert fetched is not None and fetched.quiet is True
    claimed = await store.claim_next("worker-1")
    assert claimed is not None and claimed.quiet is True


@pytest.mark.anyio
async def test_create_persists_per_job_import_settings(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(
        ["/music/a"],
        quiet=True,
        logpath="/logs/import-a.log",
        group_albums=True,
        flat=True,
        set_fields={"genre": "Jazz", "comments": "ad-hoc"},
    )
    assert (job.logpath, job.group_albums, job.flat) == ("/logs/import-a.log", True, True)
    assert job.set_fields == {"genre": "Jazz", "comments": "ad-hoc"}
    # Settings survive the DB round-trip (the worker reads them on claim, possibly in another process).
    claimed = await store.claim_next("worker-1")
    assert claimed is not None and claimed.id == job.id
    assert (claimed.logpath, claimed.group_albums, claimed.flat) == ("/logs/import-a.log", True, True)
    assert claimed.set_fields == {"genre": "Jazz", "comments": "ad-hoc"}


@pytest.mark.anyio
async def test_create_defaults_leave_settings_unset(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"])
    fetched = await store.get(job.id)
    assert fetched is not None
    for view in (job, fetched):
        assert view.logpath is None
        assert view.group_albums is False
        assert view.flat is False
        assert view.set_fields == {}


@pytest.mark.anyio
async def test_adhoc_jobs_keep_their_own_settings(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Jobs submitted with differing settings each round-trip their own values (nothing bleeds across jobs)."""
    store = _store(session_factory)
    first = await store.create(["/music/a"], group_albums=True, set_fields={"genre": "Jazz"})
    second = await store.create(["/music/b"], flat=True, logpath="/logs/b.log")
    views = {job.id: job for job in await store.list()}
    assert views[first.id].group_albums is True and views[first.id].flat is False
    assert views[first.id].set_fields == {"genre": "Jazz"} and views[first.id].logpath is None
    assert views[second.id].flat is True and views[second.id].group_albums is False
    assert views[second.id].logpath == "/logs/b.log" and views[second.id].set_fields == {}


@pytest.mark.anyio
async def test_lease_is_mutually_exclusive(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    await store.ensure_lock_row()
    assert await store.acquire_lock("worker-1", lease_seconds=30) is True
    assert await store.lock_holder() == "worker-1"
    assert await store.acquire_lock("worker-2", lease_seconds=30) is False
    assert await store.acquire_lock("worker-1", lease_seconds=30) is True


@pytest.mark.anyio
async def test_expired_lease_allows_takeover(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    await store.ensure_lock_row()
    assert await store.acquire_lock("worker-1", lease_seconds=-1) is True  # already-expired lease
    assert await store.acquire_lock("worker-2", lease_seconds=30) is True


@pytest.mark.anyio
async def test_claim_and_decision_roundtrip(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"])

    claimed = await store.claim_next("worker-1")
    assert claimed is not None and claimed.id == job.id and claimed.status is ImportJobStatus.RUNNING
    assert await store.claim_next("worker-1") is None

    await store.set_awaiting(DecisionRequest(job_id=job.id, task_id="t1", prompt="pick one"))
    awaiting = await store.get(job.id)
    assert awaiting is not None and awaiting.status is ImportJobStatus.AWAITING_DECISION
    assert awaiting.pending_decision is not None and awaiting.pending_decision.prompt == "pick one"

    assert awaiting.decision_submitted is False

    # A decision posted by *any* process is consumed by the leader exactly once.
    assert await store.submit_decision(job.id, ImportDecision(action=ImportAction.SKIP)) is True
    submitted = await store.get(job.id)
    # The UI uses this flag to keep polling while the worker consumes the answer (still AWAITING_DECISION).
    assert submitted is not None and submitted.decision_submitted is True
    assert await store.submit_decision(job.id, ImportDecision(action=ImportAction.SKIP)) is False
    taken = await store.take_decision(job.id)
    assert taken is not None and taken.action is ImportAction.SKIP
    assert await store.take_decision(job.id) is None
    resumed = await store.get(job.id)
    assert resumed is not None and resumed.status is ImportJobStatus.RUNNING and resumed.pending_decision is None


@pytest.mark.anyio
async def test_set_output_persists_and_is_exposed(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"])
    created = await store.get(job.id)
    assert created is not None and created.output is None

    await store.set_output(job.id, "Starting import of: /music/a\nImporting 'X - Y' as-is.")
    updated = await store.get(job.id)
    assert updated is not None
    assert updated.output is not None
    assert "Importing 'X - Y' as-is." in updated.output

    # Output survives a later status change (set_status doesn't touch the output column).
    await store.set_status(job.id, ImportJobStatus.COMPLETED)
    done = await store.get(job.id)
    assert done is not None and done.status is ImportJobStatus.COMPLETED and done.output == updated.output


@pytest.mark.anyio
async def test_abort_flag(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"])
    assert await store.is_abort_requested(job.id) is False
    assert await store.request_abort(job.id) is True
    assert await store.is_abort_requested(job.id) is True


@pytest.mark.anyio
async def test_recover_orphans_fails_only_other_workers_jobs(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    # A job left RUNNING by a now-dead leader, and a job legitimately owned by the new leader.
    orphan = await store.create(["/music/orphan"])
    await store.claim_next("dead-worker")  # claims `orphan` (oldest PENDING) under the dead worker
    mine = await store.create(["/music/mine"])
    await store.claim_next("new-leader")

    recovered = await store.recover_orphans("new-leader")
    assert recovered == 1
    orphan_view = await store.get(orphan.id)
    mine_view = await store.get(mine.id)
    assert orphan_view is not None and orphan_view.status is ImportJobStatus.FAILED
    assert mine_view is not None and mine_view.status is ImportJobStatus.RUNNING


@pytest.mark.anyio
async def test_path_import_is_not_a_clean_slate(session_factory: async_sessionmaker[AsyncSession]) -> None:
    job = await _store(session_factory).create(["/music/a"])
    assert job.is_clean_slate is False
    assert (job.clean_slate_album_id, job.clean_slate_item_id, job.clean_slate_allow_fewer_files) == (None, None, False)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("fields", "label"),
    [
        pytest.param({"clean_slate_album_id": 7, "clean_slate_allow_fewer_files": True}, "album", id="album"),
        pytest.param({"clean_slate_item_id": 9}, "track", id="track"),
    ],
)
async def test_create_persists_clean_slate_settings(
    session_factory: async_sessionmaker[AsyncSession], fields: dict[str, object], label: str
) -> None:
    store = _store(session_factory)
    job = await store.create(["/downloads/Artist - Album"], **fields)  # type: ignore[arg-type]

    claimed = await store.claim_next("worker-1")
    assert claimed is not None and claimed.id == job.id
    assert claimed.is_clean_slate is True
    assert claimed.paths == ["/downloads/Artist - Album"]
    assert claimed.source_label == "clean slate: Artist - Album"
    for name, value in fields.items():
        assert getattr(claimed, name) == value
    assert (claimed.clean_slate_album_id is not None) == (label == "album")


@pytest.mark.anyio
async def test_create_rejects_a_clean_slate_naming_both_ids(session_factory: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(ValueError, match="not both"):
        await _store(session_factory).create(["/downloads/x"], clean_slate_album_id=1, clean_slate_item_id=2)


async def _inference(session_factory: async_sessionmaker[AsyncSession], subject: str, beets_id: int, path: str) -> None:
    async with session_factory() as session:
        session.add(
            InferredSourcePath(
                subject_type=subject,
                beets_id=beets_id,
                source_path=path,
                method="downloader_hook",
                inferred_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.commit()


async def _inferences(session_factory: async_sessionmaker[AsyncSession]) -> set[tuple[str, int, str]]:
    async with session_factory() as session:
        rows = (await session.execute(select(InferredSourcePath))).scalars().all()
    return {(row.subject_type, row.beets_id, row.source_path) for row in rows}


@pytest.mark.anyio
async def test_retarget_moves_the_album_inference_and_drops_its_tracks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _inference(session_factory, "album", 3, "/dl/album")
    await _inference(session_factory, "track", 30, "/dl/album")
    await _inference(session_factory, "track", 31, "/dl/album")
    await _inference(session_factory, "album", 8, "/dl/stale-guess-for-reused-id")
    await _inference(session_factory, "album", 4, "/dl/other")

    await _store(session_factory).retarget_inferred_source_paths("album", 3, 8, [30, 31])

    assert await _inferences(session_factory) == {("album", 8, "/dl/album"), ("album", 4, "/dl/other")}


@pytest.mark.anyio
async def test_retarget_drops_the_inference_when_nothing_replaced_the_entry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _inference(session_factory, "album", 3, "/dl/album")
    await _inference(session_factory, "track", 30, "/dl/album")

    await _store(session_factory).retarget_inferred_source_paths("album", 3, None, [30])

    assert await _inferences(session_factory) == set()


@pytest.mark.anyio
async def test_retarget_keeps_a_track_inference_that_got_the_same_id_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _inference(session_factory, "track", 5, "/dl/song.flac")

    await _store(session_factory).retarget_inferred_source_paths("track", 5, 5, [5])

    assert await _inferences(session_factory) == {("track", 5, "/dl/song.flac")}
