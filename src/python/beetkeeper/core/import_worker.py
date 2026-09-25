"""
Leader-elected worker that runs interactive beets imports across uvicorn processes.

Every process runs `ImportWorker.run()`, but only the holder of the leased `import_lock` (see
`ImportStore.acquire_lock`) actually runs imports — so at most one import executes node-wide (the beets
library is single-writer SQLite), while every process keeps serving submit/status/decision/abort against
the shared DB-backed `ImportStore`. If the leader dies, its lease expires and another process takes over
and fails any orphaned job.

Threading bridge (unchanged from before): beets' importer is a multi-threaded pipeline, and its
interactive `choose_*` hooks run in beets' own threads. Those reach the event loop through a
`BlockingPortal`; from the loop, decisions are exchanged through the DB (so a decision POST handled by ANY
process is seen by the leader). beets dev docs: https://beets.readthedocs.io/en/v2.12.0/dev/importer.html

A clean-slate job (`ImportJob.is_clean_slate`) is a path import preceded by the removal of one existing
library entry — `beet remove -d` followed by `beet import` of the entry's raw source folder — so the same
session and decision flow applies; the removal itself lives in `core.clean_slate`.
"""

import copy
import logging
import os
import re
import socket
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

import anyio
from anyio import to_thread
from anyio.from_thread import BlockingPortal

# Subclassing requires the class at definition time; beets is a hard dependency. `Album`/`Item` must be
# runtime imports (not TYPE_CHECKING): beets inspects listener signatures on registration, evaluating the
# parameter annotations.
from beets.importer import Action, DuplicateAction, ImportSession
from beets.library import Album, Item, Library  # noqa: TC002
from beets.plugins import BeetsPlugin
from beets.util import bytestring_path
from beets.util.functemplate import ESCAPE_CHAR, Parser

from beetkeeper.core.clean_slate import CleanSlateError, RemovedEntry, preview, remove_entry, require_ok, saved_id
from beetkeeper.core.import_jobs import (  # pants: no-infer-dep
    CleanSlateTarget,
    DecisionRequest,
    ImportAction,
    ImportCandidate,
    ImportDecision,
    ImportJob,
    ImportJobStatus,
)
from beetkeeper.core.library import failed_plugin_names, library_write_limiter, open_library

if TYPE_CHECKING:
    from beetkeeper.core.import_store import ImportStore

_LOGGER = logging.getLogger(__name__)

_DUPLICATE_NARRATIVES: Final[dict[DuplicateAction, str]] = {
    DuplicateAction.SKIP: "skipping the new import",
    DuplicateAction.KEEP: "keeping both",
    DuplicateAction.REMOVE: "replacing the existing entry",
    DuplicateAction.MERGE: "merging them",
    DuplicateAction.UPGRADE: "keeping whichever copy of each track has the higher bitrate",
}

# Leader lease length and how often the holder renews it (renew well within the lease).
_LEASE_SECONDS = 30.0
_RENEW_INTERVAL = 10.0
# Poll cadences: how often a non-leader retries / the leader checks for work, and the decision-wait poll.
_IDLE_POLL = 1.5
_DECISION_POLL = 1.0
# How often the leader flushes a running job's accumulated output to the DB (so pollers see progress).
_OUTPUT_FLUSH_INTERVAL = 1.0
# Terminal-status writes are retried (a lost one would leave the job RUNNING forever — see _finalize_job).
_FINALIZE_ATTEMPTS = 5
_FINALIZE_RETRY_INTERVAL = 1.0


class _OutputBuffer:
    """
    Thread-safe, append-only accumulator for an import job's human-readable output.

    beets' importer is multi-threaded and our `WebImportSession` hooks run in those threads, so lines are
    appended under a lock. `snapshot()` returns a monotonic version (to skip redundant DB writes) plus the
    full text; the leader's flush task reads it on the event loop and persists it via `ImportStore`.
    """

    def __init__(self) -> None:
        """Start with an empty buffer at version 0."""
        self._lock = threading.Lock()
        self._lines: list[str] = []
        self._version = 0

    def append(self, line: str) -> None:
        """Append one line of output (callable from any beets pipeline thread)."""
        with self._lock:
            self._lines.append(line)
            self._version += 1

    def extend_lines(self, lines: Sequence[str]) -> None:
        """Append several indented lines under the previous one (a list in the narrative)."""
        with self._lock:
            self._lines.extend(f"  {line}" for line in lines)
            self._version += 1

    def snapshot(self) -> tuple[int, str]:
        """Return `(version, full_text)`; the version increments on every append."""
        with self._lock:
            return self._version, "\n".join(self._lines)


class _BufferLogHandler(logging.Handler):
    """A logging handler that funnels formatted records into an `_OutputBuffer` (for beets warnings/errors)."""

    def __init__(self, buffer: _OutputBuffer) -> None:
        """Bind the handler to the output buffer it writes to."""
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        """Format the record and append it to the buffer (never raises into beets' logging path)."""
        try:
            self._buffer.append(self.format(record))
        except Exception:  # a logging handler must not propagate exceptions into the caller
            self.handleError(record)


class DecisionBridge:
    """
    Bridges an interactive decision from a beets pipeline thread to the cross-process DB store.

    `request()` runs on the event loop (invoked from a beets thread via the portal): it parks the job on a
    `DecisionRequest` and polls the store until the UI's `ImportDecision` arrives (or abort is requested).
    """

    def __init__(self, store: ImportStore) -> None:
        """Bind the bridge to the shared import store."""
        self._store = store

    async def request(self, request: DecisionRequest) -> ImportDecision:
        """Publish the decision request and poll the store until answered (or aborted)."""
        await self._store.set_awaiting(request)
        while True:
            decision = await self._store.take_decision(request.job_id)
            if decision is not None:
                return decision
            if await self._store.is_abort_requested(request.job_id):
                return ImportDecision(action=ImportAction.SKIP)
            await anyio.sleep(_DECISION_POLL)


def _build_album_diff(task: Any, match: Any) -> list[str]:
    """
    Verbose, human-readable diff of what applying `match` (a beets `AlbumMatch`) changes for the album.

    Mirrors the essentials of beets' terminal `show_change` — album identity/provenance/match strength,
    changed album fields, per-track title changes, and missing/unmatched tracks — without ANSI color or
    terminal-width formatting (this goes into the job's plain-text output log). All attribute access is
    defensive (`getattr`): these are beets-internal, version-pinned objects, so a shape change degrades the
    diff rather than crashing the import. `match` is an `AlbumMatch(distance, info, mapping, extra_items,
    extra_tracks)`; `mapping` is `{library Item -> candidate TrackInfo}`.
    """
    info = getattr(match, "info", None)
    if info is None:
        return []
    distance = getattr(match, "distance", None)
    similarity = f" ({(1.0 - float(distance)) * 100:.1f}% match)" if distance is not None else ""
    year = f" ({info.year})" if getattr(info, "year", None) else ""
    source = f" [{info.data_source}]" if getattr(info, "data_source", None) else ""
    lines = [f"  Match: {getattr(info, 'artist', '?')} - {getattr(info, 'album', '?')}{year}{source}{similarity}"]

    cur_artist = getattr(task, "cur_artist", None)
    if cur_artist and cur_artist != getattr(info, "artist", None):
        lines.append(f"    Artist: {cur_artist} -> {info.artist}")
    cur_album = getattr(task, "cur_album", None)
    if cur_album and cur_album != getattr(info, "album", None):
        lines.append(f"    Album: {cur_album} -> {info.album}")

    track_changes: list[tuple[int, str]] = []
    for item, track_info in (getattr(match, "mapping", {}) or {}).items():
        cur_title = getattr(item, "title", "") or ""
        new_title = getattr(track_info, "title", "") or ""
        if cur_title != new_title:
            position = getattr(track_info, "index", None) or getattr(item, "track", None)
            label = f"(track {position}) " if position is not None else ""
            track_changes.append((position or 1_000_000, f"    {label}{cur_title or '?'} -> {new_title or '?'}"))
    if track_changes:
        lines.append("    Track changes:")
        lines.extend(line for _, line in sorted(track_changes, key=lambda row: row[0]))

    for track_info in getattr(match, "extra_tracks", []) or []:
        lines.append(f"    Missing track: {getattr(track_info, 'title', '?')}")
    for item in getattr(match, "extra_items", []) or []:
        lines.append(f"    Unmatched track: {getattr(item, 'title', '?')}")
    return lines


def _album_label(task: Any) -> str:
    """Human-readable `artist - album` label for a task (beets leaves both None on singleton/asis tasks)."""
    return f"{getattr(task, 'cur_artist', None) or '?'} - {getattr(task, 'cur_album', None) or '?'}"


def _track_label(item: Any) -> str:
    """Human-readable `artist - title` label for a singleton task's item."""
    return f"{getattr(item, 'artist', None) or '?'} - {getattr(item, 'title', None) or '?'}"


def _build_track_diff(task: Any, match: Any) -> list[str]:
    """
    Human-readable diff of what applying `match` (a beets `TrackMatch`) changes for a singleton track.

    The singleton counterpart of `_build_album_diff`, with the same defensive attribute access.
    """
    info = getattr(match, "info", None)
    if info is None:
        return []
    distance = getattr(match, "distance", None)
    similarity = f" ({(1.0 - float(distance)) * 100:.1f}% match)" if distance is not None else ""
    source = f" [{info.data_source}]" if getattr(info, "data_source", None) else ""
    lines = [f"  Match: {getattr(info, 'artist', '?')} - {getattr(info, 'title', '?')}{source}{similarity}"]
    item = getattr(task, "item", None)
    for attr, heading in (("artist", "Artist"), ("title", "Title")):
        current, new = getattr(item, attr, None), getattr(info, attr, None)
        if current and current != new:
            lines.append(f"    {heading}: {current} -> {new}")
    return lines


def _candidate_str(info: Any, attr: str) -> str | None:
    """
    A candidate `AlbumInfo` attribute as a non-empty string, else None.

    Coerces non-string values: only MusicBrainz guarantees string fields — e.g. Discogs release
    `album_id`s are ints — and `ImportCandidate` (a beets-agnostic DTO) validates strictly.
    """
    value = getattr(info, attr, None)
    return str(value) if value else None


def _album_candidate(index: int, match: Any) -> ImportCandidate:
    """Map a beets `AlbumMatch` to a candidate carrying the release attributes that tell editions apart."""
    info = getattr(match, "info", None)
    distance = getattr(match, "distance", None)
    tracks = getattr(info, "tracks", None)
    return ImportCandidate(
        index=index,
        label=f"{getattr(info, 'artist', '?')} - {getattr(info, 'album', '?')}",
        similarity=(1.0 - float(distance)) if distance is not None else None,
        data_source=_candidate_str(info, "data_source"),
        year=getattr(info, "year", None) or None,
        country=_candidate_str(info, "country"),
        media=_candidate_str(info, "media"),
        record_label=_candidate_str(info, "label"),
        catalognum=_candidate_str(info, "catalognum"),
        disambiguation=_candidate_str(info, "albumdisambig"),
        track_count=len(tracks) if tracks else None,
        album_id=_candidate_str(info, "album_id"),
        release_url=_candidate_str(info, "data_url"),
    )


def _track_candidate(index: int, match: Any) -> ImportCandidate:
    """Map a beets `TrackMatch` to a candidate (`album_id` carries the source's track id for the link column)."""
    info = getattr(match, "info", None)
    distance = getattr(match, "distance", None)
    return ImportCandidate(
        index=index,
        label=f"{getattr(info, 'artist', '?')} - {getattr(info, 'title', '?')}",
        similarity=(1.0 - float(distance)) if distance is not None else None,
        data_source=_candidate_str(info, "data_source"),
        album_id=_candidate_str(info, "track_id"),
        release_url=_candidate_str(info, "data_url"),
    )


def _session_config_overrides(job: ImportJob) -> dict[str, object]:
    """
    The job's overrides for the `import` config keys beets reads from `ImportSession.config`.

    A clean slate additionally pins `incremental` off — its source folder was, in all likelihood, imported
    before, and beets' incremental mode would silently skip it by path history — plus `resume` off, one task
    per folder (no album grouping), and singleton mode when the entry being replaced is a standalone track.
    """
    overrides: dict[str, object] = {"group_albums": job.group_albums, "flat": job.flat}
    if job.is_clean_slate:
        overrides.update(
            group_albums=False, incremental=False, resume=False, singletons=job.clean_slate_item_id is not None
        )
    return overrides


_TEMPLATE_SPECIALS: Final = re.compile(f"[{re.escape(''.join(Parser.escapable_chars))}]")


def _escape_template_literal(value: str) -> str:
    """Quote `value` so beets' path-format template engine, which evaluates every `--set` value, keeps it as is."""
    return _TEMPLATE_SPECIALS.sub(lambda match: ESCAPE_CHAR + match[0], value)


def _merged_set_fields(job: ImportJob, preserved: Mapping[str, str]) -> dict[str, str]:
    """
    The job's `set_fields` plus a clean slate's preserved fields, which win for a name both carry.

    Only the preserved values are escaped: they are literal library values, whereas the job's own entries may
    deliberately be templates (`$albumartist`).
    """
    return {**job.set_fields, **{name: _escape_template_literal(value) for name, value in preserved.items()}}


def _apply_job_import_config(job: ImportJob, preserved_fields: Mapping[str, str]) -> None:
    """
    Overlay the job's per-job settings, plus a clean slate's `preserved_fields`, onto beets' global `import` config.

    beets reads these keys from the global config while the session runs (`ImportSession.set_config` copies
    `group_albums`/`flat` at `run()`, and `ImportTask.set_fields` reads the `--set` values mid-pipeline), so
    per-job values are applied by mutating it. Safe because imports run one at a time node-wide (the leased
    leader is a single consumer) and every job sets ALL of these keys, so nothing leaks between jobs.
    """
    # Imported lazily, like the rest of beets in `core`.
    from beets import config as beets_config

    beets_config["import"]["group_albums"] = job.group_albums
    beets_config["import"]["flat"] = job.flat
    beets_config["import"]["set_fields"] = _merged_set_fields(job, preserved_fields)


def _job_loghandler(job: ImportJob) -> logging.FileHandler | None:
    """
    A handler appending beets' import log lines to the job's `logpath` (`beet import -l`), or None.

    Mirrors beets' own CLI wiring: the handler is passed to `ImportSession`, whose logger records the
    session narrative (import started, skipped/as-is paths, duplicates). The caller must `close()` it after
    the run. An unwritable path raises `OSError`, failing the job with that error.
    """
    if not job.logpath:
        return None
    return logging.FileHandler(job.logpath, encoding="utf-8")


def _failed_plugins_warning() -> str | None:
    """
    Return a hint line if any configured beets plugins failed to load (else None).

    Plugins load once per process (see `core.library._load_plugins_once`) and the failure tracebacks land
    only in the server log — usually during some earlier request, not this job — so every job repeats the
    summary: a missing plugin silently changes import behavior, and the job output is where users look.
    """
    failed = failed_plugin_names()
    if not failed:
        return None
    return (
        f"Warning: {len(failed)} configured beets plugin(s) failed to load: {', '.join(failed)}. "
        "Install the missing plugin packages in beetkeeper's environment (tracebacks are in the server log)."
    )


def _metadata_source_warning() -> str | None:
    """
    Return a hint line if autotag is on but no metadata-source plugins are loaded (else None).

    In beets 2.x MusicBrainz is a *plugin* (not built in), and a custom `plugins:` list REPLACES beets'
    default `[musicbrainz]` rather than extending it — so it's easy to disable every metadata source by
    accident, which makes autotag silently yield 0 candidates and parks every album on a manual decision.
    Call this after `open_library` (which loads the configured plugins). All access is defensive.
    """
    # Imported lazily, like the rest of beets in `core`.
    from beets import config as beets_config
    from beets import metadata_plugins

    try:
        autotag_on = bool(beets_config["import"]["autotag"].get(bool))
    except Exception:
        autotag_on = True
    if not autotag_on:
        return None
    try:
        sources = metadata_plugins.find_metadata_source_plugins()
    except Exception:
        return None
    if sources:
        return None
    return (
        "Warning: import.autotag is on but no metadata-source plugins are enabled (e.g. 'musicbrainz'). "
        "beets will find 0 candidates, so every album awaits a manual decision. Add a source plugin to the "
        "beets config's `plugins:` list."
    )


class WebImportSession(ImportSession):
    """
    A `beets.importer.ImportSession` whose interactive hooks defer to the web UI via a `BlockingPortal`.

    The `choose_*`/`resolve_*` methods run in beets' pipeline threads, so they reach the loop with
    `portal.call(...)`; decisions and the abort flag are read/written through the DB-backed store.
    """

    def __init__(
        self,
        library: Any,
        paths: Sequence[str],
        *,
        job_id: str,
        portal: BlockingPortal,
        bridge: DecisionBridge,
        store: ImportStore,
        output: _OutputBuffer,
        quiet: bool = False,
        loghandler: logging.Handler | None = None,
        config_overrides: Mapping[str, object] | None = None,
    ) -> None:
        """
        Construct the beets session and stash the async-bridge handles used by the decision hooks.

        `loghandler`, when given, becomes the session logger's handler — beets' `-l` import log.
        `config_overrides` are applied to the session's detached `import` config (see `set_config`).
        """
        # beets stores paths as bytes; `ImportSession.__init__(lib, loghandler, paths, query)`.
        super().__init__(library, loghandler, [bytestring_path(p) for p in paths], None)
        self._job_id = job_id
        self._portal = portal
        self._bridge = bridge
        self._store = store
        self._output = output
        self._quiet = quiet
        self._config_overrides = dict(config_overrides or {})

    def set_config(self, config: Any) -> None:
        """
        Run the session on a detached copy of beets' `import` config, with the job's overrides applied.

        beets reads these keys live for the whole run (`copy`/`move`/`write` once per task) from the global
        config, which other requests may touch underneath a running import; the copy keeps the job's
        overrides (and beets' own implied edits: `resume`, `incremental`, `copy`, ...) from being undone
        mid-run or leaking into later jobs. `config` is ignored: beets always passes the global view.
        """
        from beets import config as beets_config

        detached = copy.deepcopy(beets_config)["import"]
        for key, value in self._config_overrides.items():
            detached[key] = value
        super().set_config(detached)

    # beets interactive hooks below execute in beets' pipeline threads, not the event loop.

    def choose_match(self, task: Any) -> Any:
        """Ask the UI which candidate to apply for an album `task` (or to skip / import as-is)."""
        return self._choose(
            task, _album_label(task), "Choose a match for this album.", _album_candidate, _build_album_diff
        )

    def choose_item(self, task: Any) -> Any:
        """Ask the UI which candidate to apply for a singleton track `task` (or to skip / import as-is)."""
        label = _track_label(getattr(task, "item", None))
        return self._choose(task, label, "Choose a match for this track.", _track_candidate, _build_track_diff)

    def _choose(
        self,
        task: Any,
        label: str,
        prompt: str,
        to_candidate: Callable[[int, Any], ImportCandidate],
        build_diff: Callable[[Any, Any], list[str]],
    ) -> Any:
        """Shared album/singleton decision flow: honor abort + quiet mode, else park on the UI's answer."""
        if self._portal.call(self._store.is_abort_requested, self._job_id):
            self._output.append(f"Skipping '{label}' (abort requested).")
            return Action.SKIP

        if self._quiet:
            # Non-interactive (`beet import -q`): decide without prompting the UI.
            return self._quiet_choice(task, label, build_diff)

        request = self._build_decision_request(task, prompt, to_candidate)
        self._output.append(f"Matching '{label}' — {len(request.candidates)} candidate(s); awaiting decision.")
        # Blocks THIS beets thread until the UI answers (the portal runs `bridge.request` on the loop).
        decision = self._portal.call(self._bridge.request, request)

        if decision.action is ImportAction.SKIP:
            self._output.append(f"Skipped '{label}'.")
            return Action.SKIP
        if decision.action is ImportAction.ASIS:
            self._output.append(f"Importing '{label}' as-is (tags unchanged).")
            return Action.ASIS
        # TODO[Claude]: validate `candidate_index` against `task.candidates`; handle empty/None.
        index = decision.candidate_index or 0
        chosen = request.candidates[index].label if index < len(request.candidates) else f"#{index}"
        match = task.candidates[index]
        self._output.append(f"Applying candidate '{chosen}' to '{label}':")
        for line in build_diff(task, match):
            self._output.append(line)
        return match

    def _quiet_choice(
        self, task: Any, album_label: str, build_diff: Callable[[Any, Any], list[str]] = _build_album_diff
    ) -> Any:
        """
        Decide a match without prompting (the `beet import -q` rule).

        Apply the best candidate iff beets rates the match a *strong* recommendation; otherwise fall back to
        beets' `import.quiet_fallback` config (skip by default, or import as-is).
        """
        # Imported here (not at module load) to keep beets internals lazy, like the rest of `core`.
        from beets.autotag import Recommendation

        candidates = getattr(task, "candidates", None) or []
        if candidates and getattr(task, "rec", None) is Recommendation.strong:
            match = candidates[0]  # beets sorts candidates best-first
            self._output.append(f"Quiet import: applying strong match for '{album_label}':")
            for line in build_diff(task, match):
                self._output.append(line)
            return match

        fallback = self._quiet_fallback_action()
        if fallback is Action.ASIS:
            self._output.append(f"Quiet import: no strong match for '{album_label}' — importing as-is.")
        else:
            self._output.append(f"Quiet import: no strong match for '{album_label}' — skipping.")
        return fallback

    @staticmethod
    def _quiet_fallback_action() -> Any:
        """Map beets' `import.quiet_fallback` config to an action (defaults to SKIP, matching beets)."""
        from beets import config as beets_config

        try:
            choice = str(beets_config["import"]["quiet_fallback"].get())
        except Exception:  # config missing/unreadable — fall back to the safe default
            choice = "skip"
        return Action.ASIS if choice == "asis" else Action.SKIP

    def get_duplicate_action(self, task: Any, found_duplicates: Any) -> Any:
        """
        Resolve an import that duplicates existing library entries per beets' `import.duplicate_action`.

        The base class returns the configured action (`skip`/`keep`/`remove`/`merge`/`ask`). There is no
        interactive duplicate prompt here yet, so `ask` (beets' default) degrades to the same safe choice
        as `beet import -q`: skip the new import.
        """
        # TODO[Claude]: bridge `ask` to the UI as a DecisionRequest (skip / keep / remove / merge).
        action = super().get_duplicate_action(task, found_duplicates)
        suffix = ""
        if action is DuplicateAction.ASK:
            action = DuplicateAction.SKIP
            suffix = " ('ask' is not supported in web imports yet)"
        label = _album_label(task) if getattr(task, "is_album", True) else _track_label(getattr(task, "item", None))
        self._output.append(
            f"'{label}' duplicates an existing library entry — {_DUPLICATE_NARRATIVES[action]}{suffix}."
        )
        return action

    def should_resume(self, path: Any) -> bool:
        """Whether to resume a previously-interrupted import for `path` (scaffold: never)."""
        # TODO[Claude]: surface resume as a decision instead of always declining.
        return False

    def _build_decision_request(
        self,
        task: Any,
        prompt: str = "Choose a match for this album.",
        to_candidate: Callable[[int, Any], ImportCandidate] = _album_candidate,
    ) -> DecisionRequest:
        """
        Map a beets `task` and its candidates into a serializable `DecisionRequest`.

        `to_candidate` builds each `ImportCandidate` (`_album_candidate` carries the differentiating release
        attributes so the UI can tell otherwise-identical candidates apart; `_track_candidate` is the
        singleton counterpart). All attribute access is defensive (beets-internal objects).
        """
        candidates = [to_candidate(index, match) for index, match in enumerate(getattr(task, "candidates", []))]
        return DecisionRequest(
            job_id=self._job_id,
            task_id=str(id(task)),
            prompt=prompt,
            candidates=candidates,
            allowed_actions=[ImportAction.APPLY, ImportAction.ASIS, ImportAction.SKIP],
        )


class _ImportNarrator:
    """
    Thread-safe narrator of what a running import adds, fed by beets' import events.

    beets' pipeline fires `album_imported`/`item_imported` from its worker threads as each task's files
    land in the library, so the count is locked and the narrative output line is emitted live per event.
    This is purely job-output narration — persisting import events is exclusively the beetkeeper plugin's
    job (it POSTs them to `/api/events`); the server never records import events on its own.
    """

    def __init__(self, output: _OutputBuffer) -> None:
        """Bind the narrator to the job's output buffer (for the per-event narrative lines)."""
        self._lock = threading.Lock()
        self._output = output
        self._imported_count = 0
        self.imported_album_ids: list[int] = []
        self.imported_item_ids: list[int] = []

    def album_imported(self, album: Album) -> None:
        """Narrate one imported album and its track count."""
        item_count = len(list(album.items()))
        with self._lock:
            self._imported_count += 1
            self.imported_album_ids.append(saved_id(album))
        self._output.append(
            f"Imported album: {album.albumartist or '?'} - {album.album or '?'} ({item_count} track(s))."
        )

    def item_imported(self, item: Item) -> None:
        """Narrate one imported standalone (singleton) track."""
        with self._lock:
            self._imported_count += 1
            self.imported_item_ids.append(saved_id(item))
        self._output.append(f"Imported standalone track: {item.artist or '?'} - {item.title or '?'}.")

    @property
    def imported_count(self) -> int:
        """Number of albums + standalone tracks narrated so far."""
        with self._lock:
            return self._imported_count


class _ImportEventsPlugin(BeetsPlugin):
    """
    Routes beets' `album_imported`/`item_imported` events to the currently-running job's narrator.

    beets dispatches events from the process-global `BeetsPlugin.listeners` registry, which has no
    unregister API — so exactly one instance is created lazily (`_import_events`) and lives for the
    process, forwarding to whichever narrator is installed on `self.narrator`. The worker runs at most
    one import at a time per process, so a single slot suffices; events with no narrator installed
    (imports run by other beets clients while we're idle) are ignored.
    """

    def __init__(self) -> None:
        """Register the import-event listeners (a one-time, process-global side effect)."""
        super().__init__(name="beetkeeper")
        self.narrator: _ImportNarrator | None = None
        self.register_listener("album_imported", self._on_album_imported)
        self.register_listener("item_imported", self._on_item_imported)

    def _on_album_imported(self, lib: Library, album: Album) -> None:
        if self.narrator is not None:
            self.narrator.album_imported(album)

    def _on_item_imported(self, lib: Library, item: Item) -> None:
        if self.narrator is not None:
            self.narrator.item_imported(item)


# The singleton lives in a dict so it can be set without `global` (mirrors `library._plugins_state`).
_import_events_lock = threading.Lock()
_import_events_state: dict[str, _ImportEventsPlugin] = {}


def _import_events() -> _ImportEventsPlugin:
    """The process-wide import-events listener plugin, created (and registered) on first use."""
    with _import_events_lock:
        if "plugin" not in _import_events_state:
            _import_events_state["plugin"] = _ImportEventsPlugin()
        return _import_events_state["plugin"]


@dataclass
class _ImportRunResult:
    """
    What one `_run_import_blocking` did, for the post-run bookkeeping on the event loop.

    Filled in as the run progresses (the caller keeps a reference), so a clean slate's removal is known even
    when the import that follows raises.
    """

    removed: RemovedEntry | None = None
    imported_album_ids: list[int] = field(default_factory=list)
    imported_item_ids: list[int] = field(default_factory=list)


class ImportWorker:
    """
    Per-process import runner; only the lease holder actually runs imports (see module docstring).

    Launch `run()` as a background task in the FastAPI lifespan. Submit/answer/abort/status all go through
    the shared `ImportStore` (not this object), so they work no matter which process handles the request.
    """

    def __init__(
        self,
        beets_config_filepath: Path,
        store: ImportStore,
        downloads_path: Path | None = None,
        *,
        preserve_fields: Collection[str] = (),
    ) -> None:
        """
        Create the worker over the shared store; mint a unique-per-process worker id.

        `downloads_path` (beetkeeper's `downloads_path` setting) bounds clean-slate source folders; a clean-slate
        job fails up front when it is unset. `preserve_fields` names the flexible attributes a clean slate carries
        onto its fresh import (see `core.clean_slate`).
        """
        self._beets_config_filepath = beets_config_filepath
        self._store = store
        self._downloads_path = downloads_path
        self._preserve_fields = tuple(preserve_fields)
        self._bridge = DecisionBridge(store)
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._was_leader = False

    async def run(self) -> None:
        """
        Leader loop: acquire/renew the lease, recover orphans on election, then claim + run jobs.

        The lock row is ensured once up front, unguarded: migrations have just run, so a failure there is
        a real misconfiguration that should fail startup loudly. After that, each cycle is guarded against
        any `Exception` (transient SQLite contention, aiosqlite surfacing cancellation as "no active
        connection", driver errors that are not `OperationalError`, or child-task errors wrapped by anyio
        in an `ExceptionGroup`): the error is logged and the cycle retried, so a DB hiccup never kills the
        worker for the process's lifetime. Cancellation derives from `BaseException` and still exits
        promptly via the `anyio.sleep` checkpoint.
        """
        await self._store.ensure_lock_row()
        async with BlockingPortal() as portal:
            while True:
                try:
                    await self._run_one_cycle(portal)
                except Exception:
                    _LOGGER.warning("Import worker cycle failed; retrying.", exc_info=True)
                    await anyio.sleep(_IDLE_POLL)

    async def _run_one_cycle(self, portal: BlockingPortal) -> None:
        """One leader-loop cycle: try for the lease, recover orphans on election, claim + run one job."""
        if not await self._store.acquire_lock(self._worker_id, _LEASE_SECONDS):
            self._was_leader = False
            await anyio.sleep(_IDLE_POLL)
            return
        if not self._was_leader:
            recovered = await self._store.recover_orphans(self._worker_id)
            if recovered:
                _LOGGER.warning(f"Failed {recovered} orphaned import job(s) on becoming import leader.")
            # Flipped only AFTER recovery succeeds, so a recovery interrupted by a transient DB error
            # (absorbed by run()'s retry guard) is re-attempted on the next cycle instead of skipped.
            self._was_leader = True
        job = await self._store.claim_next(self._worker_id)
        if job is None:
            await anyio.sleep(_IDLE_POLL)
            return
        await self._run_job(job, portal)

    async def _run_job(self, job: ImportJob, portal: BlockingPortal) -> None:
        output = _OutputBuffer()
        failure: Exception | None = None
        result = _ImportRunResult()
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self._renew_lease_until_cancelled)
            # Flush the growing output to the DB so anyone polling the job renders progress live.
            task_group.start_soon(self._flush_output_until_cancelled, job.id, output)
            try:
                # Run the multi-threaded beets pipeline on one worker thread; the lease is renewed
                # concurrently so we keep leadership across long imports / decision waits. Holding
                # `library_write_limiter` for the duration upholds the app-wide invariant that at most
                # one beets-library writer exists (the UI's modify/remove wait until the import ends).
                await to_thread.run_sync(
                    self._run_import_blocking, job, portal, output, result, limiter=library_write_limiter
                )
            except Exception as exc:  # keep the worker alive; the failure lands on the job below
                failure = exc
            finally:
                # Stop the renew/flush tasks BEFORE the terminal writes below: a flush holding a
                # pre-append snapshot could otherwise land after (and clobber) the final output.
                task_group.cancel_scope.cancel()
        status = ImportJobStatus.FAILED
        if failure is None:
            try:
                aborted = await self._store.is_abort_requested(job.id)
                output.append("Import aborted." if aborted else "Import completed.")
                status = ImportJobStatus.ABORTED if aborted else ImportJobStatus.COMPLETED
            except Exception as exc:  # bookkeeping failed — the job must still reach a terminal state
                failure = exc
        if failure is not None:
            _LOGGER.error(f"Import job {job.id} failed.", exc_info=failure)
            output.append(f"Import failed: {failure}")
        await self._finalize_job(job.id, output, status, error=str(failure) if failure is not None else None)
        if result.removed is not None:
            await self._retarget_inferences(job, result)

    async def _retarget_inferences(self, job: ImportJob, result: _ImportRunResult) -> None:
        """
        Move the clean-slated entry's inferred source path onto its fresh import, or drop it (best-effort).

        Guarded like the other post-import bookkeeping: a failure here is logged and never fails the job,
        whose library changes are already done.
        """
        removed = result.removed
        assert removed is not None
        imported = result.imported_album_ids if removed.target.subject == "album" else result.imported_item_ids
        new_id = imported[0] if len(imported) == 1 else None
        try:
            await self._store.retarget_inferred_source_paths(
                removed.target.subject, removed.target.beets_id, new_id, removed.item_ids
            )
        except Exception:
            _LOGGER.warning(f"Re-keying the inferred source path after clean-slate job {job.id} failed.", exc_info=True)

    async def _finalize_job(
        self, job_id: str, output: _OutputBuffer, status: ImportJobStatus, *, error: str | None
    ) -> None:
        """
        Persist the job's final output and terminal status, retrying DB errors.

        Losing the terminal write would leave the job RUNNING forever: `claim_next` only claims PENDING
        jobs and `recover_orphans` spares this worker's own claims, so nothing else could repair it while
        this process lives.
        """
        for attempt in range(1, _FINALIZE_ATTEMPTS + 1):
            try:
                await self._store.set_output(job_id, output.snapshot()[1])
                await self._store.set_status(job_id, status, error=error)
                return
            except Exception:
                _LOGGER.warning(
                    f"Persisting terminal state for import job {job_id} failed "
                    f"(attempt {attempt}/{_FINALIZE_ATTEMPTS}).",
                    exc_info=True,
                )
                if attempt < _FINALIZE_ATTEMPTS:
                    await anyio.sleep(_FINALIZE_RETRY_INTERVAL)
        _LOGGER.error(
            f"Import job {job_id} could not be marked {status.value}; it stays RUNNING until orphan "
            "recovery fails it after a restart."
        )

    async def _renew_lease_until_cancelled(self) -> None:
        """
        Renew the leader lease periodically; any error skips one renewal, never the running import.

        Guarded with a broad `except Exception`: an escaping exception would cancel `_run_job`'s task
        group (anyio wraps it in an `ExceptionGroup`), aborting the import over a background renewal blip.
        """
        while True:
            await anyio.sleep(_RENEW_INTERVAL)
            try:
                await self._store.acquire_lock(self._worker_id, _LEASE_SECONDS)
            except Exception:
                _LOGGER.warning("Import lease renewal failed; retrying on the next interval.", exc_info=True)

    async def _flush_output_until_cancelled(self, job_id: str, output: _OutputBuffer) -> None:
        """
        Persist the job's output to the DB whenever it grows (so pollers see incremental progress).

        Any error skips this flush (without advancing the version, so the same text is retried next
        interval) rather than aborting the running import — see `_renew_lease_until_cancelled` on why the
        guard is broad.
        """
        last_version = -1
        while True:
            await anyio.sleep(_OUTPUT_FLUSH_INTERVAL)
            version, text = output.snapshot()
            if version == last_version:
                continue
            try:
                await self._store.set_output(job_id, text)
            except Exception:
                _LOGGER.warning("Import output flush failed; retrying on the next interval.", exc_info=True)
                continue
            last_version = version

    def _run_import_blocking(
        self, job: ImportJob, portal: BlockingPortal, output: _OutputBuffer, result: _ImportRunResult | None = None
    ) -> _ImportRunResult:
        """
        Open the library, run the clean-slate removal (if any) and the beets import to completion, narrating.

        Executes in a worker thread (beets connections are thread-local). The added albums/items are
        narrated through beets' own `album_imported`/`item_imported` events (fired by the pipeline as each
        task lands — see `_ImportEventsPlugin`). beets warnings/errors during the run are funneled into
        `output` alongside the session's own narrative lines. A clean slate that fails its guard raises before
        the library is touched, failing the job. `result` (a fresh one when omitted) is filled in as the run
        progresses and returned.
        """
        result = result if result is not None else _ImportRunResult()
        if job.is_clean_slate:
            output.append(f"Starting clean-slate import of: {', '.join(job.paths)}")
        else:
            output.append(f"Starting import of: {', '.join(job.paths)}")
        handler = _BufferLogHandler(output)
        handler.setLevel(logging.WARNING)  # only surface beets warnings/errors; our hooks emit the narrative
        handler.setFormatter(logging.Formatter("beets %(levelname)s: %(message)s"))
        beets_logger = logging.getLogger("beets")
        beets_logger.addHandler(handler)
        try:
            library = open_library(self._beets_config_filepath)
            for warning in (_failed_plugins_warning(), _metadata_source_warning()):
                if warning is not None:
                    output.append(warning)
            preserved: Mapping[str, str] = {}
            if job.is_clean_slate:
                result.removed, preserved = self._clean_slate_blocking(job, library, output)
            _apply_job_import_config(job, preserved)
            loghandler = _job_loghandler(job)
            session = WebImportSession(
                library,
                job.paths,
                job_id=job.id,
                portal=portal,
                bridge=self._bridge,
                store=self._store,
                output=output,
                quiet=job.quiet,
                loghandler=loghandler,
                config_overrides=_session_config_overrides(job),
            )
            events = _import_events()
            narrator = _ImportNarrator(output)
            events.narrator = narrator
            try:
                session.run()  # blocks until beets' pipeline finishes (or drains via cooperative SKIP on abort)
            finally:
                events.narrator = None
                if loghandler is not None:
                    loghandler.close()
            if narrator.imported_count == 0:
                output.append(
                    f"Nothing was imported. The removed entry is gone from the library; its source files remain at "
                    f"{job.paths[0]} for a later import."
                    if result.removed is not None
                    else "No new items were added to the library."
                )
            result.imported_album_ids = list(narrator.imported_album_ids)
            result.imported_item_ids = list(narrator.imported_item_ids)
            return result
        finally:
            beets_logger.removeHandler(handler)

    def _clean_slate_blocking(
        self, job: ImportJob, library: Library, output: _OutputBuffer
    ) -> tuple[RemovedEntry, dict[str, str]]:
        """
        Re-run the clean-slate preview as the guard, narrate the plan, then remove the entry.

        Returns the removal record plus the preserved field values the import that follows re-applies.

        Raises `CleanSlateError` (failing the job, library untouched) when the entry or source changed since
        the job was submitted in a way the preview rejects.
        """
        if self._downloads_path is None:
            raise CleanSlateError("invalid", "This worker has no downloads_path configured; clean slates need one.")
        if len(job.paths) != 1:
            raise CleanSlateError("invalid", "A clean-slate job imports exactly one source path.")
        target = CleanSlateTarget.from_ids(job.clean_slate_album_id, job.clean_slate_item_id)
        plan = preview(
            library,
            target,
            job.paths[0],
            downloads_path=self._downloads_path,
            allow_fewer_files=job.clean_slate_allow_fewer_files,
            preserve_fields=self._preserve_fields,
        )
        require_ok(plan)
        output.append(
            f"Clean slate for {plan.subject} '{plan.label}' (#{plan.beets_id}): {plan.item_count} library row(s), "
            f"{plan.files_present} file(s) on disk, {plan.files_missing} missing; the source folder holds "
            f"{plan.source_audio_files} audio file(s)."
        )
        if plan.files_to_delete:
            output.append(f"Deleting {len(plan.files_to_delete)} library file(s):")
            output.extend_lines(plan.files_to_delete)
        if plan.art_to_delete:
            output.append(f"Deleting album art: {plan.art_to_delete}")
        if plan.files_kept_outside_library:
            output.append(f"Leaving {len(plan.files_kept_outside_library)} file(s) outside the library untouched:")
            output.extend_lines(plan.files_kept_outside_library)
        if plan.fields_preserved:
            kept = ", ".join(f"{name}={value}" for name, value in plan.fields_preserved.items())
            output.append(f"Preserving fields (re-applied to the new import): {kept}.")
            overridden = [name for name in plan.fields_preserved if name in job.set_fields]
            if overridden:
                output.append(f"The job's set_fields for {', '.join(overridden)} are ignored: the entry's values win.")
        if plan.flexible_attributes_lost:
            output.append(f"Flexible attributes not carried over: {', '.join(plan.flexible_attributes_lost)}.")
        for warning in plan.warnings:
            output.append(f"Warning: {warning}")
        return remove_entry(library, target, job.paths[0], narrate=output.append), plan.fields_preserved
