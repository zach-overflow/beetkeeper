"""
Bridges the downloader hook (`beetkeeper.hooks`), the beets library and the `inferred_source_path` table for
the source-path lookup routes. A successful lookup is persisted as an *inference* — kept apart from the
event-backed recorded source paths, which come exclusively from the beetkeeper plugin (see `db.models`).
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from beetkeeper.api.api_models.import_api_models import FindMissingSourcePathRequest, FindMissingSourcePathResponse
from beetkeeper.api.constants import LibrarySubject
from beetkeeper.core import BeetsLibrary
from beetkeeper.db.models import InferredSourcePath
from beetkeeper.hooks import DownloaderHook

DOWNLOADER_HOOK_METHOD = "downloader_hook"


async def find_missing_source_path(
    library: BeetsLibrary, downloader: DownloaderHook, session: AsyncSession, request: FindMissingSourcePathRequest
) -> FindMissingSourcePathResponse | None:
    """
    Look the entry up by beets id, search the downloader with its configured fields, and persist a match.

    Returns None when no library entry has that id.
    """
    lookup = library.get_albums if request.is_album else library.get_tracks
    entry = (await lookup([request.beets_id])).get(request.beets_id)
    if entry is None:
        return None
    params = downloader.query_params(entry)
    result = await downloader.search(params)
    if result.found and result.source_path is not None:
        await record_inferred_source_path(session, request.subject, request.beets_id, result.source_path, params)
    return FindMissingSourcePathResponse.from_search(result, params, recorded_inference=result.found)


async def record_inferred_source_path(
    session: AsyncSession, subject: LibrarySubject, beets_id: int, source_path: str, query_params: dict[str, str]
) -> None:
    """Upsert the entry's inferred source path (a fresh lookup replaces any earlier inference)."""
    await session.execute(
        delete(InferredSourcePath).where(
            col(InferredSourcePath.subject_type) == subject.value, col(InferredSourcePath.beets_id) == beets_id
        )
    )
    session.add(
        InferredSourcePath(
            subject_type=subject.value,
            beets_id=beets_id,
            source_path=source_path,
            method=DOWNLOADER_HOOK_METHOD,
            query_params_json=json.dumps(query_params),
            inferred_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await session.commit()


async def inferred_source_paths(
    session: AsyncSession, subject: LibrarySubject, beets_ids: Sequence[int]
) -> dict[int, str]:
    """Inferred source paths keyed by beets id, for the given subject type (ids with none are omitted)."""
    if not beets_ids:
        return {}
    rows = (
        await session.execute(
            select(col(InferredSourcePath.beets_id), col(InferredSourcePath.source_path)).where(
                col(InferredSourcePath.subject_type) == subject.value,
                col(InferredSourcePath.beets_id).in_(set(beets_ids)),
            )
        )
    ).all()
    return {beets_id: source_path for beets_id, source_path in rows}
