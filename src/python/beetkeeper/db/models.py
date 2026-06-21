"""
Any database ORM models needed for our `core` and `api` to properly function.
Model definitions should be subclassed from `SQLModel` rather than SQLAlchemy models.
"""

# TODO: add whatever relevant datamodels as SQlModel classes. See the following links for inspiration:
# https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/models.py
# https://sqlmodel.tiangolo.com/#sql-databases-in-fastapi
from datetime import UTC, datetime
from enum import StrEnum, unique

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def _get_datetime_utc() -> datetime:
    return datetime.now(UTC)


@unique
class JobType(StrEnum):
    """Example starting point for describing the types of 'job' entries our app might model."""

    IMPORT = "import"
    DELETE = "delete"


@unique
class JobStatus(StrEnum):
    """Example classifications of the possible status of any given job our app might model."""

    FAILED = "failed"
    RUNNING = "running"
    SUCCESS = "success"


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
