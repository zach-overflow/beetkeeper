from collections import defaultdict
from collections.abc import Callable, Collection, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnElement
from sqlmodel import col

from beetkeeper.api.api_models import (
    APIAlbum,
    APITrack,
    EventDisplayRecord,
    EventSearchResult,
    EventSubjectSummary,
    ListenerEventDetails,
)
from beetkeeper.api.constants import EventLookupEntityType
from beetkeeper.constants import BeetsEventType
from beetkeeper.db.models import AlbumEvent, ImportDestinationPath, ImportSourcePath, ListenerEvent, TrackEvent

if TYPE_CHECKING:
    from beetkeeper.core.library import BeetsLibrary

_EVENT_TYPES_WITH_ALBUM_ROWS = frozenset({BeetsEventType.ALBUM_IMPORTED, BeetsEventType.ALBUM_REMOVED})
_EVENT_TYPES_WITH_TRACK_ROWS = frozenset(
    {BeetsEventType.TRACK_IMPORTED, BeetsEventType.TRACK_REMOVED, BeetsEventType.IMPORT_TASK_FILES}
)
_EVENT_TYPES_WITH_PATH_ROWS = frozenset({BeetsEventType.IMPORT_TASK_FILES})
_MERGE_PARTNER_MAX_SKEW = timedelta(minutes=1)
_MERGED_EVENT_LABELS = {
    BeetsEventType.ALBUM_IMPORTED: "Album imported",
    BeetsEventType.TRACK_IMPORTED: "Singleton imported",
}


def _event_ids_of_types(events: Sequence[ListenerEvent], event_types: frozenset[BeetsEventType]) -> list[int]:
    """
    The ids of `events` whose type is one of `event_types`.

    Which child tables an event type writes is fixed by the `/api/events/*` push routes (see
    `beetkeeper.api.api_routes.events_router`), so the listing skips child-table queries that cannot match.
    """
    return [event.event_id for event in events if event.event_id is not None and event.event_type in event_types]


class _ListenerEventChild(Protocol):
    """A row of one of `listener_event`'s child tables (the `*_event` and `import_*_path` models)."""

    listener_event_id: int | None


async def _recent_listener_events(session: AsyncSession, offset: int, limit: int) -> Sequence[ListenerEvent]:
    """One page of `listener_event` rows, newest first (`pushed_at` desc, ties broken by `event_id` desc)."""
    return (
        (
            await session.execute(
                select(ListenerEvent)
                .order_by(col(ListenerEvent.pushed_at).desc(), col(ListenerEvent.event_id).desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def _child_rows[ChildT: _ListenerEventChild](
    session: AsyncSession, model: type[ChildT], listener_event_ids: Sequence[int]
) -> Sequence[ChildT]:
    """The `model` rows belonging to `listener_event_ids`; no query runs when there are no ids."""
    if not listener_event_ids:
        return []
    return (
        (await session.execute(select(model).where(col(model.listener_event_id).in_(listener_event_ids))))
        .scalars()
        .all()
    )


def _grouped_by_event[ChildT: _ListenerEventChild, ValueT](
    rows: Sequence[ChildT], value_of: Callable[[ChildT], ValueT]
) -> dict[int, list[ValueT]]:
    """`value_of(row)` for every row, grouped by the row's listener event id (row order kept within an event)."""
    grouped: defaultdict[int, list[ValueT]] = defaultdict(list)
    for row in rows:
        grouped[cast("int", row.listener_event_id)].append(value_of(row))
    return grouped


def _album_summary(album_row: AlbumEvent) -> EventSubjectSummary:
    """The album summary an `album_event` row records."""
    return EventSubjectSummary(beets_id=album_row.beets_album_id, name=album_row.album_name)


def _track_summary(track_row: TrackEvent) -> EventSubjectSummary:
    """The track summary a `track_event` row records."""
    return EventSubjectSummary(beets_id=track_row.beets_item_id, name=track_row.track_title)


def _append_import_release_summaries(
    albums_by_event: dict[int, list[EventSubjectSummary]],
    track_rows: Sequence[TrackEvent],
    import_task_files_event_ids: Collection[int],
) -> None:
    """
    Adds each `import_task_files` event's imported releases to `albums_by_event`, derived from its track rows
    since those events push no album rows of their own.
    """
    for track_row in track_rows:
        listener_event_id = cast("int", track_row.listener_event_id)
        if listener_event_id in import_task_files_event_ids:
            _append_album_summary(
                albums_by_event.setdefault(listener_event_id, []),
                beets_album_id=track_row.beets_album_id,
                album_name=track_row.album_name,
            )


# TODO[https://github.com/zach-overflow/beetkeeper/issues/75]: Add async, non-blocking logging here.
async def listener_event_records_lookup(session: AsyncSession, offset: int, limit: int) -> list[ListenerEventDetails]:
    """
    Queries the `beetkeeper` events table ordered from newest to oldest. This is the underlying bridge between
    the beetkeeper UI / API surfacing `beetsplug.beetkeeper_plugin` events information pushed from the
    `beetsplug.beetkeeper_plugin` event listener.
    """
    recent_events = await _recent_listener_events(session, offset, limit)
    album_event_ids = _event_ids_of_types(recent_events, _EVENT_TYPES_WITH_ALBUM_ROWS)
    track_event_ids = _event_ids_of_types(recent_events, _EVENT_TYPES_WITH_TRACK_ROWS)
    path_event_ids = _event_ids_of_types(recent_events, _EVENT_TYPES_WITH_PATH_ROWS)
    album_rows = await _child_rows(session, AlbumEvent, album_event_ids)
    track_rows = await _child_rows(session, TrackEvent, track_event_ids)
    source_path_rows = await _child_rows(session, ImportSourcePath, path_event_ids)
    destination_path_rows = await _child_rows(session, ImportDestinationPath, path_event_ids)

    albums_by_event = _grouped_by_event(album_rows, _album_summary)
    _append_import_release_summaries(albums_by_event, track_rows, frozenset(path_event_ids))
    tracks_by_event = _grouped_by_event(track_rows, _track_summary)
    source_paths_by_event = _grouped_by_event(source_path_rows, lambda row: row.source_path)
    destination_paths_by_event = _grouped_by_event(destination_path_rows, lambda row: row.destination_path)

    event_records: list[ListenerEventDetails] = []
    for event in recent_events:
        event_id = cast("int", event.event_id)
        event_records.append(
            ListenerEventDetails(
                event_type=BeetsEventType(event.event_type),
                pushed_at=event.pushed_at,
                albums=albums_by_event.get(event_id, []),
                tracks=tracks_by_event.get(event_id, []),
                source_paths=source_paths_by_event.get(event_id, []),
                destination_paths=destination_paths_by_event.get(event_id, []),
            )
        )
    return event_records


def _append_album_summary(
    summaries: list[EventSubjectSummary], beets_album_id: int | None, album_name: str | None
) -> None:
    """
    Adds a track row's release to an `import_task_files` event's album summaries, keeping one summary
    per beets album id (or per bare release name for singletons, whose tracks carry no album id).
    """
    if beets_album_id is None and album_name is None:
        return
    if beets_album_id is not None and any(summary.beets_id == beets_album_id for summary in summaries):
        return
    summary = EventSubjectSummary(beets_id=beets_album_id, name=album_name)
    if summary not in summaries:
        summaries.append(summary)


def merge_import_event_records(event_records: Sequence[ListenerEventDetails]) -> list[EventDisplayRecord]:
    """
    Builds the events-UI display rows, folding each import's push pair into a single record.

    A beets import task pushes `import_task_files` immediately followed by `album_imported` (album import)
    or `item_imported` (singleton import), so listing pushes verbatim shows every import as two rows. Each
    pair merges into one record labeled "Album imported" / "Singleton imported" that keeps the later
    push's timestamp and adopts the `import_task_files` record's paths and album/track summaries (so a
    singleton row carries its release name, which only the `import_task_files` push knows). Records with no
    partner in `event_records` (removals, one half's push having failed) pass through with their raw event
    type as the label. Display-only: the stored rows and the JSON `GET /api/events` listing keep one record
    per push.

    `event_records` must be ordered newest-first (the `listener_event_records_lookup` order).
    """
    display_records: list[EventDisplayRecord] = []
    partner_indexes: set[int] = set()
    for index, event_record in enumerate(event_records):
        if index in partner_indexes:
            continue
        partner_index = _import_task_files_partner_index(event_records, index, partner_indexes)
        if partner_index is None:
            display_records.append(_display_record(event_record))
            continue
        partner_indexes.add(partner_index)
        display_records.append(_merged_display_record(event_record, event_records[partner_index]))
    return display_records


def _display_record(event_record: ListenerEventDetails) -> EventDisplayRecord:
    return EventDisplayRecord(
        event_label=event_record.event_type.value,
        pushed_at=event_record.pushed_at,
        albums=event_record.albums,
        tracks=event_record.tracks,
        source_paths=event_record.source_paths,
        destination_paths=event_record.destination_paths,
    )


def _merged_display_record(event_record: ListenerEventDetails, partner: ListenerEventDetails) -> EventDisplayRecord:
    return EventDisplayRecord(
        event_label=_MERGED_EVENT_LABELS[event_record.event_type],
        pushed_at=event_record.pushed_at,
        albums=_ordered_union(event_record.albums, partner.albums),
        tracks=_ordered_union(event_record.tracks, partner.tracks),
        source_paths=partner.source_paths,
        destination_paths=partner.destination_paths,
    )


def _subject_key(summary: EventSubjectSummary) -> int | str | None:
    return summary.beets_id if summary.beets_id is not None else summary.name


def _ordered_union(first: list[EventSubjectSummary], second: list[EventSubjectSummary]) -> list[EventSubjectSummary]:
    """
    Union keyed on the beets id (falling back to the name for id-less singleton releases), keeping
    `first`'s entries — its names come from the imported event's own album/track rows — over `second`'s.
    """
    first_keys = {_subject_key(summary) for summary in first}
    return first + [summary for summary in second if _subject_key(summary) not in first_keys]


def _import_task_files_partner_index(
    event_records: Sequence[ListenerEventDetails], record_index: int, partner_indexes: set[int]
) -> int | None:
    """
    The index of the `import_task_files` record paired with the imported-event record at `record_index`,
    or None when that record is not a pairable `album_imported`/`item_imported` or has no partner.

    The plugin pushes `import_task_files` immediately before the imported event of the same task, so the
    partner is the nearest older unpaired `import_task_files` record sharing a beets album id (album
    imports) or track id (singleton imports) — bounded to `_MERGE_PARTNER_MAX_SKEW`, so a matching record
    from an unrelated earlier import never pairs.
    """
    event_record = event_records[record_index]
    if event_record.event_type is BeetsEventType.ALBUM_IMPORTED and event_record.album_ids:
        pairing_ids = frozenset(event_record.album_ids)
    elif event_record.event_type is BeetsEventType.TRACK_IMPORTED and event_record.track_ids:
        pairing_ids = frozenset(event_record.track_ids)
    else:
        return None
    pair_on_album_ids = event_record.event_type is BeetsEventType.ALBUM_IMPORTED
    for candidate_index in range(record_index + 1, len(event_records)):
        candidate = event_records[candidate_index]
        if abs(event_record.pushed_at - candidate.pushed_at) > _MERGE_PARTNER_MAX_SKEW:
            return None
        if (
            candidate_index not in partner_indexes
            and candidate.event_type is BeetsEventType.IMPORT_TASK_FILES
            and not pairing_ids.isdisjoint(candidate.album_ids if pair_on_album_ids else candidate.track_ids)
        ):
            return candidate_index
    return None


def _defined_fields(subject_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Drop null fields from a beets library dict so `APIAlbum`/`APITrack` field defaults apply.

    The generated models type some fields from beets' shipped defaults (e.g. `artpath: bytes`), but a real
    library row can hold NULL there — validating None would fail where omitting the key does not.
    """
    return {key: value for key, value in subject_dict.items() if value is not None}


async def _query_listener_event_join(
    session: AsyncSession,
    beets_library: BeetsLibrary,
    join_events_table: type[AlbumEvent | TrackEvent],
    conditions: Sequence[ColumnElement[bool]],
    offset: int = 0,
    limit: int | None = None,
) -> list[EventSearchResult]:
    """
    Helper for running a JOIN query between `ListenerEvent` and one of its child tables for event search.

    Each matched `(child event, listener event)` row becomes one `EventSearchResult` (newest first). The
    matched beets album/item ids are looked up in the beets library in one batch; ids with no match yield
    a null `current_beets_subject_state` (the subject no longer exists in the beets library).
    """
    rows = (
        await session.execute(
            select(join_events_table, ListenerEvent)
            .join(ListenerEvent)
            .where(*conditions)
            .order_by(col(ListenerEvent.pushed_at).desc(), col(ListenerEvent.event_id).desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    if not rows:
        return []
    subject_models: dict[int, APIAlbum | APITrack]
    if join_events_table is AlbumEvent:
        beets_ids = [child_event.beets_album_id for child_event, _ in rows]
        album_dicts = await beets_library.get_albums(beets_ids)
        subject_models = {
            beets_id: APIAlbum(**_defined_fields(album_dict)) for beets_id, album_dict in album_dicts.items()
        }
    else:
        beets_ids = [child_event.beets_item_id for child_event, _ in rows]
        track_dicts = await beets_library.get_tracks(beets_ids)
        subject_models = {
            beets_id: APITrack(**_defined_fields(track_dict)) for beets_id, track_dict in track_dicts.items()
        }
    return [
        EventSearchResult(
            event_id=cast("int", listener_event.event_id),
            event_type=BeetsEventType(listener_event.event_type),
            event_time=listener_event.pushed_at,
            beets_id=beets_id,
            current_beets_subject_state=subject_models.get(beets_id),
        )
        for (_, listener_event), beets_id in zip(rows, beets_ids, strict=True)
    ]


async def listener_event_lookup_by_type_and_id(
    entity_type: EventLookupEntityType,
    entity_id: int,
    session: AsyncSession,
    offset: int,
    limit: int,
    beets_library: BeetsLibrary,
) -> list[EventSearchResult]:
    """
    Queries and returns the list of beetkeeper events associated with the provided ID, if any exist. This coroutine is
    generalized to handle the various similar `GET /events/{type}/{ID}` beetkeeper route handlers. In other words, this
    needs to support lookups by Beetkeeper event ID, beets album ID, or beets item ID (all mutually exclusive).
    """
    if entity_type is EventLookupEntityType.ALBUM:
        return await _query_listener_event_join(
            session=session,
            beets_library=beets_library,
            join_events_table=AlbumEvent,
            conditions=[col(AlbumEvent.beets_album_id) == entity_id],
            offset=offset,
            limit=limit,
        )
    if entity_type is EventLookupEntityType.TRACK:
        return await _query_listener_event_join(
            session=session,
            beets_library=beets_library,
            join_events_table=TrackEvent,
            conditions=[col(TrackEvent.beets_item_id) == entity_id],
            offset=offset,
            limit=limit,
        )
    # BKEVENT: one listener event's children span (at most) both child tables, so the two queries are run
    # unpaginated and the page is sliced from the combined result (a single event's children are few).
    album_results = await _query_listener_event_join(
        session=session,
        beets_library=beets_library,
        join_events_table=AlbumEvent,
        conditions=[col(AlbumEvent.listener_event_id) == entity_id],
    )
    track_results = await _query_listener_event_join(
        session=session,
        beets_library=beets_library,
        join_events_table=TrackEvent,
        conditions=[col(TrackEvent.listener_event_id) == entity_id],
    )
    return (album_results + track_results)[offset : offset + limit]
