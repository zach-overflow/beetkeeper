"""
beetkeeper-DB lookups backing the `/search` page: the import source paths recorded for beets subjects.

Source paths exist only for imports the `beetkeeper` beets plugin reported (an `import_task_files` push
writes `ImportSourcePath` rows plus one `TrackEvent` row per imported item, all sharing the listener event
id). Subjects with no such rows were imported without the plugin's event tracking, so the lookups simply
omit them — the UI renders that absence explicitly.
"""

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from sqlmodel import col

from beetkeeper.db.models import ImportSourcePath, TrackEvent


async def _import_source_paths_by_key(
    session: AsyncSession, key_column: Mapped[int] | Mapped[int | None], keys: Sequence[int]
) -> dict[int, list[str]]:
    """Distinct recorded source paths per `key_column` value, newest import first."""
    if not keys:
        return {}
    rows = (
        await session.execute(
            select(key_column, col(ImportSourcePath.source_path))
            .select_from(TrackEvent)
            .join(ImportSourcePath, col(ImportSourcePath.listener_event_id) == col(TrackEvent.listener_event_id))
            .where(key_column.in_(set(keys)))
            .order_by(col(TrackEvent.listener_event_id).desc(), col(ImportSourcePath.id))
        )
    ).all()
    source_paths_by_key: dict[int, list[str]] = defaultdict(list)
    for key, source_path in rows:
        if source_path not in source_paths_by_key[key]:
            source_paths_by_key[key].append(source_path)
    return dict(source_paths_by_key)


async def import_source_paths_by_track_id(session: AsyncSession, beets_item_ids: Sequence[int]) -> dict[int, list[str]]:
    """Recorded import source paths keyed by beets item id (ids with no recorded import are omitted)."""
    return await _import_source_paths_by_key(session, col(TrackEvent.beets_item_id), beets_item_ids)


async def import_source_paths_by_album_id(
    session: AsyncSession, beets_album_ids: Sequence[int]
) -> dict[int, list[str]]:
    """Recorded import source paths keyed by beets album id (ids with no recorded import are omitted)."""
    return await _import_source_paths_by_key(session, col(TrackEvent.beets_album_id), beets_album_ids)
