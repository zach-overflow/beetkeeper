"""
Any database ORM models needed for our `core` and `api` to properly function.
Model definitions should be subclassed from `SQLModel` rather than SQLAlchemy models.
"""

# TODO: add whatever relevant datamodels as SQlModel classes. See the following links for inspiration:
# https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/models.py
# https://sqlmodel.tiangolo.com/#sql-databases-in-fastapi
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def _get_datetime_utc() -> datetime:
    return datetime.now(UTC)


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
    listener_event_id: int | None = Field(default=None, foreign_key="listener_event.id", ondelete="CASCADE")
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
    listener_event_id: int | None = Field(default=None, foreign_key="listener_event.id", ondelete="CASCADE")
    beets_item_id: int


# TODO[Claude]: This `Job` is an example only. Before relying on it:
#   - Add `table=True` to any model that must persist — `class Job(SQLModel, table=True)`. As written
#     this is a plain (non-table) model and will not create/persist a table.
#   - Reconsider `ended_at`'s `default_factory=_get_datetime_utc`: a freshly-created RUNNING job would
#     already carry an end time. It should likely default to `None` and be set on completion.
class Job(SQLModel):
    """
    Example db ORM model class, which could be used directly in our FastAPI route functions (see example link below),
    and/or used in the `beetkeeper.core` module for internal logic and db interactions.
    """

    id: int | None = Field(default=None, primary_key=True)
    job_type: JobType
    created_at: datetime | None = Field(default_factory=_get_datetime_utc, sa_type=DateTime)
    ended_at: datetime | None = Field(default_factory=_get_datetime_utc, sa_type=DateTime)
    status: JobStatus | None = Field(default=None)
