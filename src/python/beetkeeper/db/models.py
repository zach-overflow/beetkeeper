"""
Any database ORM models needed for our `core` and `api` to properly function.
Model definitions should be subclassed from `SQLModel` rather than SQLAlchemy models.
"""

# https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/models.py
# https://sqlmodel.tiangolo.com/#sql-databases-in-fastapi
from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class ListenerEvent(SQLModel, table=True):
    """Append-only full history of beets events types, their lib model type, and associated model IDs."""

    __tablename__ = "listener_event"
    event_id: int | None = Field(default=None, primary_key=True)
    event_type: str
    pushed_at: datetime = Field(sa_type=DateTime)


class AlbumEvent(SQLModel, table=True):
    """
    One of several child tables to `listener_event`. Listener events can have zero, 1, or many album instances
    associated with them.
    """

    __tablename__ = "album_event"
    # https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/cascade-delete-relationships/?h=foreign#foreign-key-constraint-support
    # NOTE: have to set pragma in sqllite to enable foreing key constraints
    id: int | None = Field(default=None, primary_key=True)
    listener_event_id: int | None = Field(default=None, foreign_key="listener_event.event_id", ondelete="CASCADE")
    beets_album_id: int


class TrackEvent(SQLModel, table=True):
    """
    One of several child tables to `listener_event`. Listener events can have zero, 1, or many track instances
    associated with them.
    """

    __tablename__ = "track_event"
    # https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/cascade-delete-relationships/?h=foreign#foreign-key-constraint-support
    # NOTE: have to set pragma in sqllite to enable foreing key constraints
    id: int | None = Field(default=None, primary_key=True)
    listener_event_id: int | None = Field(default=None, foreign_key="listener_event.event_id", ondelete="CASCADE")
    beets_item_id: int
    beets_album_id: int | None = Field(default=None)


# TODO: draft — not wired up yet. Re-enable once it has a migration and a valid `import_job` FK
# (note: `import_job`'s primary key is `id` (a str), not `event_id`).
#
# Feasibility / how to build (investigated 2026-06-27): the source -> destination data is available for free
# from beets. During the importer's `manipulate_files` stage, `beets.library.Item.move_file()` emits
# `item_copied` / `item_moved` / `item_linked` / `item_hardlinked` / `item_reflinked` events, each carrying
# `item` (-> `item.id`), `source`, and `destination` (bytes paths). beets dispatches events via the
# class-level `BeetsPlugin.listeners` table, so beetkeeper can register one in-process listener (a tiny
# `BeetsPlugin` whose `register_listener(...)` runs in beets' pipeline threads) WITHOUT loading config
# plugins, collect rows into a thread-safe sink, then have the leader worker persist them after the import
# (mirroring the existing output-buffer / `record_import_events` patterns in `core/import_worker.py`).
# Schema notes for re-enabling: make `dst_path` unique + indexed (one row per imported file; re-imports
# upsert), index `src_path` for reverse lookups, decode the bytes paths to str, and consider `ondelete=
# "SET NULL"` (not CASCADE) so this "canonical ledger" survives pruning of transient `import_job` rows.
# Caveat: only audio Items emit these events — non-audio extras (cover art, logs) are moved by filetote and
# would need its events to be captured too.
# class FileLineage(SQLModel, table=True):
#     """
#     Persists the per-file lineage of any given file / directory in the beets-managed library folder, and
#     associated raw, un-processed input filepath, if any.
#
#     This is particularly helpful for tracking down the original raw file(s) from a given import, and
#     also may prove useful for users debugging their beets config.
#     """
#     __tablename__ = "file_lineage"
#     id: str = Field(primary_key=True)
#     dst_path: str
#     src_path: str
#     import_job_id: int | None = Field(default=None, foreign_key="import_job.event_id", ondelete="CASCADE")


class ImportJobRecord(SQLModel, table=True):
    """
    Persisted state of one interactive import job (see `beetkeeper.core.import_store`).

    This is the cross-process source of truth: any uvicorn worker reads/writes it, while the leader-elected
    import worker runs the actual beets import. `paths` and the decision request/response are stored as JSON
    text. `status` holds an `ImportJobStatus` value; `claimed_by` is the worker id currently running it.
    """

    __tablename__ = "import_job"
    id: str = Field(primary_key=True)
    status: str
    paths_json: str
    created_at: datetime = Field(sa_type=DateTime)
    updated_at: datetime = Field(sa_type=DateTime)
    claimed_by: str | None = Field(default=None)
    error: str | None = Field(default=None)
    abort_requested: bool = Field(default=False)
    # Non-interactive (`beet import -q`) mode: the worker auto-decides matches instead of prompting.
    quiet: bool = Field(default=False)
    # Per-job import settings mirroring `beet import` flags (`-l`, `--group-albums`, `--flat`, `--set`);
    # captured at submit time so each ad-hoc import keeps its own values. `set_fields_json` is a JSON object.
    logpath: str | None = Field(default=None)
    group_albums: bool = Field(default=False)
    flat: bool = Field(default=False)
    set_fields_json: str | None = Field(default=None)
    # Serialized `DecisionRequest` the worker is parked on; serialized `ImportDecision` the UI posted back.
    pending_decision_json: str | None = Field(default=None)
    submitted_decision_json: str | None = Field(default=None)
    # Human-readable, append-only log of the import's progress (rendered on the job's UI fragment). The
    # leader flushes it to the DB as the import runs, so any process polling the job sees it incrementally.
    output: str | None = Field(default=None)


class ImportLock(SQLModel, table=True):
    """
    Single-row (id=1) leased lock electing the one process that runs imports node-wide.

    Acquired/renewed with an atomic conditional UPDATE; the lease (`lease_expires_at`) lets another process
    take over if the holder dies. This serializes imports across uvicorn workers (the beets library is
    single-writer SQLite) without a separate broker.
    """

    __tablename__ = "import_lock"
    id: int = Field(default=1, primary_key=True)
    holder: str | None = Field(default=None)
    lease_expires_at: datetime | None = Field(default=None, sa_type=DateTime)
