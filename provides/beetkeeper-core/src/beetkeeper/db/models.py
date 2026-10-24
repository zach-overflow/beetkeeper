"""
Any database ORM models needed for our `core` and `api` to properly function.
Model definitions should be subclassed from `SQLModel` rather than SQLAlchemy models.

All `DateTime` columns are stored naive-UTC (SQLite's DATETIME is tz-naive); write them with `naive_utcnow`
and compare naive against naive.

See:
    https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/models.py
    https://sqlmodel.tiangolo.com/#sql-databases-in-fastapi
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, UniqueConstraint
from sqlmodel import AutoString, Field, SQLModel

from beetkeeper.constants import BeetsEventType


def naive_utcnow() -> datetime:
    """Naive UTC 'now' matching the tz-naive `DateTime` columns below."""
    return datetime.now(UTC).replace(tzinfo=None)


class ListenerEvent(SQLModel, table=True):
    """Append-only full history of beets events types, their lib model type, and associated model IDs."""

    __tablename__ = "listener_event"
    # Serves the newest-first listing's `ORDER BY pushed_at DESC, event_id DESC` via a reverse index scan.
    __table_args__ = (Index("ix_listener_event_pushed_at_event_id", "pushed_at", "event_id"),)
    event_id: int | None = Field(default=None, primary_key=True)
    # `sa_type` keeps the column a plain string: SQLModel's default enum mapping (`sa.Enum`) would persist
    # member *names* (breaking rows already stored as values) and add a CHECK constraint with no migration.
    event_type: BeetsEventType = Field(sa_type=AutoString)
    pushed_at: datetime = Field(sa_type=DateTime)


class AlbumEvent(SQLModel, table=True):
    """
    One of several child tables to `listener_event`. Listener events can have zero, 1, or many album instances
    associated with them.
    """

    __tablename__ = "album_event"
    id: int | None = Field(default=None, primary_key=True)
    listener_event_id: int | None = Field(
        default=None, foreign_key="listener_event.event_id", ondelete="CASCADE", index=True
    )
    beets_album_id: int = Field(index=True)
    album_name: str | None = Field(default=None)


class TrackEvent(SQLModel, table=True):
    """
    One of several child tables to `listener_event`. Listener events can have zero, 1, or many track instances
    associated with them.
    """

    __tablename__ = "track_event"
    id: int | None = Field(default=None, primary_key=True)
    listener_event_id: int | None = Field(
        default=None, foreign_key="listener_event.event_id", ondelete="CASCADE", index=True
    )
    beets_item_id: int = Field(index=True)
    beets_album_id: int | None = Field(default=None)
    track_title: str | None = Field(default=None)
    album_name: str | None = Field(default=None)


class ImportSourcePath(SQLModel, table=True):
    """Records of import events' corresponding source filepath(s) prior to beets importing them."""

    __tablename__ = "import_source_path"
    id: int | None = Field(default=None, primary_key=True)
    listener_event_id: int | None = Field(
        default=None, foreign_key="listener_event.event_id", ondelete="CASCADE", index=True
    )
    source_path: str


class ImportDestinationPath(SQLModel, table=True):
    """Records of import events' corresponding destination filepath(s) after beets imported them."""

    __tablename__ = "import_destination_path"
    id: int | None = Field(default=None, primary_key=True)
    listener_event_id: int | None = Field(
        default=None, foreign_key="listener_event.event_id", ondelete="CASCADE", index=True
    )
    destination_path: str


class InferredSourcePath(SQLModel, table=True):
    """
    A library entry's pre-import source path as *inferred* through an opt-in integration (`beetkeeper.hooks`),
    for entries whose import the beetkeeper plugin never reported.

    Deliberately separate from the event-backed `import_source_path` ledger: recorded paths come exclusively
    from plugin events, and an inference is a best guess the UI labels as such. One row per entry (a fresh
    lookup replaces it). `subject_type` is `album` or `track`; `method` names the integration that answered.
    """

    __tablename__ = "inferred_source_path"
    __table_args__ = (UniqueConstraint("subject_type", "beets_id", name="uq_inferred_source_path_subject"),)
    id: int | None = Field(default=None, primary_key=True)
    subject_type: str
    beets_id: int
    source_path: str
    method: str
    query_params_json: str | None = Field(default=None)
    inferred_at: datetime = Field(sa_type=DateTime)


class AuthSessionRecord(SQLModel, table=True):
    """
    One logged-in session created by `POST /api/auth/login` (see `beetkeeper.api.security`).

    Sessions live in the DB (not process memory) so they survive restarts and are visible to every process
    sharing the database. Only a SHA-256 hex digest of the bearer token is stored — the raw token is returned
    once to the client and never persisted.
    """

    __tablename__ = "auth_session"
    token_hash: str = Field(primary_key=True)
    created_at: datetime = Field(sa_type=DateTime)
    expires_at: datetime = Field(sa_type=DateTime)


class ImportJobRecord(SQLModel, table=True):
    """
    Persisted state of one interactive import job (see `beetkeeper.core.import_store`).

    This is the cross-process source of truth: any process reads/writes it, while the leader-elected import
    worker runs the actual beets import. `status` holds an `ImportJobStatus` value and `claimed_by` the worker
    id currently running it. The `*_json` columns hold JSON text: `paths_json` the import paths,
    `set_fields_json` the `--set` object, `pending_decision_json` the `DecisionRequest` the worker is parked
    on and `submitted_decision_json` the `ImportDecision` the UI posted back. `output` is the append-only
    progress log the leader flushes as the import runs, so pollers see it incrementally. The per-job import
    settings are captured at submit time so each ad-hoc import keeps its own values; their meanings are
    documented on `core.import_jobs.ImportJob`.
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
    quiet: bool = Field(default=False)
    logpath: str | None = Field(default=None)
    group_albums: bool = Field(default=False)
    flat: bool = Field(default=False)
    set_fields_json: str | None = Field(default=None)
    clean_slate_album_id: int | None = Field(default=None)
    clean_slate_item_id: int | None = Field(default=None)
    clean_slate_allow_fewer_files: bool = Field(default=False)
    pending_decision_json: str | None = Field(default=None)
    submitted_decision_json: str | None = Field(default=None)
    output: str | None = Field(default=None)


class ImportLock(SQLModel, table=True):
    """
    Single-row (id=1) leased lock electing the one process that runs imports node-wide.

    Acquired/renewed with an atomic conditional UPDATE; the lease (`lease_expires_at`) lets another process
    take over if the holder dies. This serializes imports across processes (the beets library is
    single-writer SQLite) without a separate broker.
    """

    __tablename__ = "import_lock"
    id: int = Field(default=1, primary_key=True)
    holder: str | None = Field(default=None)
    lease_expires_at: datetime | None = Field(default=None, sa_type=DateTime)
