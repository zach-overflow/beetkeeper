"""
This module contains the database layer: ORM models and (TODO) engine/session wiring.

TODO[Claude]: The persistence layer is unspecified and needs design before any db-backed endpoint:
    - Engine + session: no `create_engine`/async engine, sessionmaker, or `get_session` FastAPI
      dependency exists yet. Decide sync vs. async (anyio-compatible) sessions per CLAUDE.md.
    - Connection URL source: where does the DB live (e.g. SQLite path)? `UserConfig` currently has no
      DB-path/DSN field — add one in `beetkeeper/settings/user_config.py` and read it here.
    - Schema creation/migrations: see `db/alembic/` — alembic is scaffolded but empty (no env.py/ini).
"""

from beetkeeper.db.models import Job, JobStatus, JobType

__all__ = ["Job", "JobStatus", "JobType"]
