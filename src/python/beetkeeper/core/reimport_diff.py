"""
Prior-vs-new diffing for library-mode reimports (`beet import -L`).

A reimport replaces library entries in place: beets removes the old rows and adds fresh ones carrying the
newly-chosen metadata. `ReimportDiffCollector` snapshots each task's items as beets creates the task (the
values still in the library), then diffs them against the same item objects once beets has applied the match
and handled their files. The result is a `ReimportReport` — most usefully, the fields a reimport *dropped*.

The collector is fed from beets' pipeline threads by `import_worker._ImportEventsPlugin`, so its state is
locked. It also guards the run by dropping two kinds of task up front:
  * entries whose files no longer exist on disk — beets would raise on moving/writing such a file and take the
    whole import down. They are listed in the report for the user to restore or remove.
  * album tracks matched by a singleton-mode (`-s`) reimport — beets would re-add them as standalone tracks,
    silently detaching them from their album.
"""

import os
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from beets.util import syspath

from beetkeeper.core.import_jobs import (
    FieldChange,
    MissingFilesEntry,
    ReimportEntry,
    ReimportReport,
    TrackChange,
    is_blank_value,
)

Snapshot = dict[str, str | None]

# Bookkeeping fields beets rewrites on every reimport; diffing them is pure noise.
_IGNORED_FIELDS: Final[frozenset[str]] = frozenset({"id", "album_id", "mtime", "added"})
# Bounds the persisted report: reimporting a whole library would otherwise store a diff per album.
MAX_REPORT_ENTRIES: Final[int] = 200


def item_snapshot(item: Any) -> Snapshot:
    """The item's own stored fields (fixed + flexible, no computed or album-inherited ones) as text.

    Values go through beets' per-field formatting rather than `str()`: a raw value's representation is not
    stable across a reimport (a boolean reads back from SQLite as `0` but is `False` once beets re-applies
    it), which would otherwise surface as phantom changes.
    """
    formatted = item.formatted()
    return {key: formatted[key] for key in item.keys(computed=False, with_album=False) if key not in _IGNORED_FIELDS}


def diff_snapshots(old: Snapshot, new: Snapshot) -> list[FieldChange]:
    """Field-level changes from `old` to `new`, sorted by field name (blank-to-blank is not a change)."""
    changes: list[FieldChange] = []
    for field in sorted(old.keys() | new.keys()):
        before, after = old.get(field), new.get(field)
        if before == after or (is_blank_value(before) and is_blank_value(after)):
            continue
        changes.append(FieldChange(field=field, old=before, new=after))
    return changes


def _track_label(snapshot: Snapshot) -> str:
    return f"{snapshot.get('artist') or '?'} - {snapshot.get('title') or '?'}"


def _task_items(task: Any) -> list[Any]:
    """The library items a task covers (an album task's tracks, or a singleton task's one item)."""
    if getattr(task, "is_album", True):
        return list(getattr(task, "items", None) or [])
    item = getattr(task, "item", None)
    return [item] if item is not None else []


def _task_label(task: Any, snapshots: Sequence[Snapshot]) -> str:
    if not snapshots:
        return "?"
    first = snapshots[0]
    if getattr(task, "is_album", True):
        return f"{first.get('albumartist') or first.get('artist') or '?'} - {first.get('album') or '?'}"
    return _track_label(first)


def _hoist_shared_changes(tracks: list[TrackChange]) -> tuple[list[FieldChange], list[TrackChange]]:
    """Split out the changes every track shares (album-level edits) so they are reported once."""
    if len(tracks) < 2:
        return [], tracks
    shared = set(tracks[0].changes).intersection(*(track.changes for track in tracks[1:]))
    if not shared:
        return [], tracks
    remaining = [
        track.model_copy(update={"changes": [change for change in track.changes if change not in shared]})
        for track in tracks
    ]
    return sorted(shared, key=lambda change: change.field), remaining


@dataclass(frozen=True)
class _PendingTask:
    # Holds the item objects themselves: beets mutates them in place, and the reference keeps `id(item)`
    # from being recycled while the task is in flight.
    label: str
    items: list[tuple[Any, Snapshot]]


class ReimportDiffCollector:
    """Builds a `ReimportReport` from beets' per-task import events (see the module docstring)."""

    def __init__(self, narrate: Callable[[str], None]) -> None:
        """Bind the collector to the job-output sink used for its narrative lines."""
        self._narrate = narrate
        self._lock = threading.Lock()
        self._pending: dict[int, _PendingTask] = {}
        self._entries: list[ReimportEntry] = []
        self._missing: list[MissingFilesEntry] = []
        self._truncated = False

    def task_created(self, task: Any) -> list[Any] | None:
        """Snapshot a new task's items. Returns `[]` (beets then drops the task) for a guarded task."""
        items = _task_items(task)
        snapshots = [item_snapshot(item) for item in items]
        label = _task_label(task, snapshots)
        if not getattr(task, "is_album", True) and any(getattr(item, "album_id", None) for item in items):
            self._narrate(
                f"Skipping '{label}': it belongs to an album, and a singleton reimport would detach it. "
                "Reimport its album instead."
            )
            return []
        missing = [
            snapshot.get("path") or "?"
            for item, snapshot in zip(items, snapshots, strict=True)
            if not os.path.exists(syspath(item.path))
        ]
        if missing:
            self._narrate(
                f"Skipping '{label}': {len(missing)} of {len(items)} file(s) no longer exist on disk "
                f"({', '.join(missing)}). Restore the file(s) or remove the library entries, then reimport."
            )
            with self._lock:
                self._missing.append(MissingFilesEntry(label=label, paths=missing))
            return []
        with self._lock:
            self._pending[id(task)] = _PendingTask(label=label, items=list(zip(items, snapshots, strict=True)))
        return None

    def task_choice(self, task: Any) -> None:
        """Forget a task the user (or quiet mode) skipped: nothing is reimported, so there is no diff."""
        if getattr(task, "skip", False):
            with self._lock:
                self._pending.pop(id(task), None)

    def task_files(self, task: Any) -> None:
        """Diff a task's items now that beets has applied the match and stored them."""
        with self._lock:
            pending = self._pending.pop(id(task), None)
        if pending is None:
            return
        imported_ids = {id(item) for item in task.imported_items()}
        tracks: list[TrackChange] = []
        left_behind: list[str] = []
        for item, before in pending.items:
            if id(item) not in imported_ids:
                left_behind.append(_track_label(before))
                continue
            changes = diff_snapshots(before, item_snapshot(item))
            tracks.append(TrackChange(label=_track_label(before), path=before.get("path") or "?", changes=changes))
        shared, tracks = _hoist_shared_changes(tracks)
        entry = ReimportEntry(label=pending.label, shared_changes=shared, tracks=tracks, left_behind=left_behind)
        self._narrate(_entry_summary(entry))
        with self._lock:
            if len(self._entries) < MAX_REPORT_ENTRIES:
                self._entries.append(entry)
            else:
                self._truncated = True

    def report(self) -> ReimportReport:
        """The report accumulated so far (safe to call while the import is still running)."""
        with self._lock:
            return ReimportReport(
                entries=list(self._entries), missing_files=list(self._missing), truncated=self._truncated
            )


def _entry_summary(entry: ReimportEntry) -> str:
    all_changes = [*entry.shared_changes, *(change for track in entry.tracks for change in track.changes)]
    dropped = sum(1 for change in all_changes if change.dropped)
    summary = f"Reimported '{entry.label}': {len(all_changes)} field change(s)"
    if dropped:
        summary += f", {dropped} of which lost their previous value"
    if entry.left_behind:
        summary += f"; {len(entry.left_behind)} track(s) not covered by the match stay under the old album entry"
    return summary + "."
