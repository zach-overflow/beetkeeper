"""Tests for the cross-process coordination primitives in `ImportStore` (run against a migrated temp DB).

These prove the multi-worker behaviour: a single leased leader, atomic claim, the DB-mediated decision
handoff, cooperative abort, and orphan recovery on leader takeover.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.core import ImportAction, ImportDecision, ImportedAlbum, ImportedEntities, ImportJobStatus, ImportStore
from beetkeeper.core.import_jobs import DecisionRequest
from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent


def _store(session_factory: async_sessionmaker[AsyncSession]) -> ImportStore:
    return ImportStore(session_factory)


@pytest.mark.anyio
async def test_create_get_list(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a", "/music/b"])
    assert job.status is ImportJobStatus.PENDING
    assert job.paths == ["/music/a", "/music/b"]
    assert job.quiet is False  # interactive by default

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
async def test_lease_is_mutually_exclusive(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    await store.ensure_lock_row()
    assert await store.acquire_lock("worker-1", lease_seconds=30) is True
    assert await store.lock_holder() == "worker-1"
    assert await store.acquire_lock("worker-2", lease_seconds=30) is False  # held by worker-1
    assert await store.acquire_lock("worker-1", lease_seconds=30) is True  # holder may renew


@pytest.mark.anyio
async def test_expired_lease_allows_takeover(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    await store.ensure_lock_row()
    assert await store.acquire_lock("worker-1", lease_seconds=-1) is True  # already-expired lease
    assert await store.acquire_lock("worker-2", lease_seconds=30) is True  # worker-2 takes over


@pytest.mark.anyio
async def test_claim_and_decision_roundtrip(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"])

    claimed = await store.claim_next("worker-1")
    assert claimed is not None and claimed.id == job.id and claimed.status is ImportJobStatus.RUNNING
    assert await store.claim_next("worker-1") is None  # nothing left to claim

    await store.set_awaiting(DecisionRequest(job_id=job.id, task_id="t1", prompt="pick one"))
    awaiting = await store.get(job.id)
    assert awaiting is not None and awaiting.status is ImportJobStatus.AWAITING_DECISION
    assert awaiting.pending_decision is not None and awaiting.pending_decision.prompt == "pick one"

    assert awaiting.decision_submitted is False  # nothing answered yet

    # A decision posted by *any* process is consumed by the leader exactly once.
    assert await store.submit_decision(job.id, ImportDecision(action=ImportAction.SKIP)) is True
    submitted = await store.get(job.id)
    # The UI uses this flag to keep polling while the worker consumes the answer (still AWAITING_DECISION).
    assert submitted is not None and submitted.decision_submitted is True
    assert await store.submit_decision(job.id, ImportDecision(action=ImportAction.SKIP)) is False  # already answered
    taken = await store.take_decision(job.id)
    assert taken is not None and taken.action is ImportAction.SKIP
    assert await store.take_decision(job.id) is None  # consumed
    resumed = await store.get(job.id)
    assert resumed is not None and resumed.status is ImportJobStatus.RUNNING and resumed.pending_decision is None


@pytest.mark.anyio
async def test_set_output_persists_and_is_exposed(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    job = await store.create(["/music/a"])
    created = await store.get(job.id)
    assert created is not None and created.output is None  # no output until the worker writes some

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
async def test_record_import_events_writes_listener_rows(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    imported = ImportedEntities(albums=[ImportedAlbum(album_id=7, item_ids=[11, 12])], singleton_item_ids=[99])
    await store.record_import_events(imported)

    async with session_factory() as session:
        listeners = (await session.execute(select(ListenerEvent))).scalars().all()
        albums = (await session.execute(select(AlbumEvent))).scalars().all()
        tracks = (await session.execute(select(TrackEvent))).scalars().all()

    # 1 album_imported + 2 item_imported (in-album) + 1 item_imported (singleton).
    assert sorted(le.event_type for le in listeners) == [
        "album_imported",
        "item_imported",
        "item_imported",
        "item_imported",
    ]
    assert len(albums) == 1 and albums[0].beets_album_id == 7
    assert {(t.beets_item_id, t.beets_album_id) for t in tracks} == {(11, 7), (12, 7), (99, None)}
    # Every child row is linked to a real parent listener event.
    listener_ids = {le.event_id for le in listeners}
    assert all(a.listener_event_id in listener_ids for a in albums)
    assert all(t.listener_event_id in listener_ids for t in tracks)


@pytest.mark.anyio
async def test_record_import_events_noop_when_empty(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    await store.record_import_events(ImportedEntities())
    async with session_factory() as session:
        assert (await session.execute(select(ListenerEvent))).scalars().all() == []


@pytest.mark.anyio
async def test_recover_orphans_fails_only_other_workers_jobs(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = _store(session_factory)
    # A job left RUNNING by a now-dead leader, and a job legitimately owned by the new leader.
    orphan = await store.create(["/music/orphan"])
    await store.claim_next("dead-worker")  # claims `orphan` (oldest PENDING) under the dead worker
    mine = await store.create(["/music/mine"])
    await store.claim_next("new-leader")  # claims `mine`

    recovered = await store.recover_orphans("new-leader")
    assert recovered == 1
    orphan_view = await store.get(orphan.id)
    mine_view = await store.get(mine.id)
    assert orphan_view is not None and orphan_view.status is ImportJobStatus.FAILED
    assert mine_view is not None and mine_view.status is ImportJobStatus.RUNNING
