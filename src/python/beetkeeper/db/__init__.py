"""
beetkeeper's own database layer.

    - `models.py`     — SQLModel ORM tables: the beets-event history, import jobs + the leader lock,
                        login sessions, and inferred source paths.
    - `session.py`    — async engine + `async_sessionmaker` + the `get_session` FastAPI dependency.
    - `migrations.py` — programmatic alembic integration (online + offline `--sql`).
    - `alembic/`      — the alembic environment (`env.py` + `versions/`); migrations OWN the schema, so
                        `SQLModel.metadata.create_all` is intentionally not used at runtime.

The connection URL comes from `UserConfig.database` (see `beetkeeper.settings`).
"""

from beetkeeper.db.models import AlbumEvent, ListenerEvent, TrackEvent
from beetkeeper.db.session import get_session, make_engine, make_sessionmaker

__all__ = ["AlbumEvent", "ListenerEvent", "TrackEvent", "get_session", "make_engine", "make_sessionmaker"]
