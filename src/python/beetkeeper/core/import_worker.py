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
"""

import logging
import os
import socket
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import anyio
from anyio import to_thread
from anyio.from_thread import BlockingPortal

# Subclassing requires the class at definition time; beets is a hard dependency.
from beets.importer import Action, ImportSession
from beets.util import bytestring_path

from beetkeeper.core.import_jobs import (  # pants: no-infer-dep
    DecisionRequest,
    ImportAction,
    ImportCandidate,
    ImportDecision,
    ImportedAlbum,
    ImportedEntities,
    ImportJob,
    ImportJobStatus,
)
from beetkeeper.core.library import open_library

if TYPE_CHECKING:
    from beetkeeper.core.import_store import ImportStore

_LOGGER = logging.getLogger(__name__)

# Leader lease length and how often the holder renews it (renew well within the lease).
_LEASE_SECONDS = 30.0
_RENEW_INTERVAL = 10.0
# Poll cadences: how often a non-leader retries / the leader checks for work, and the decision-wait poll.
_IDLE_POLL = 1.5
_DECISION_POLL = 1.0
# How often the leader flushes a running job's accumulated output to the DB (so pollers see progress).
_OUTPUT_FLUSH_INTERVAL = 1.0


class _OutputBuffer:
    """Thread-safe, append-only accumulator for an import job's human-readable output.

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
    """Bridges an interactive decision from a beets pipeline thread to the cross-process DB store.

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
    """Verbose, human-readable diff of what applying `match` (a beets `AlbumMatch`) changes for the album.

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


def _metadata_source_warning() -> str | None:
    """Return a hint line if autotag is on but no metadata-source plugins are loaded (else None).

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


class WebImportSession(ImportSession):  # beets is untyped; base resolves to Any
    """A `beets.importer.ImportSession` whose interactive hooks defer to the web UI via a `BlockingPortal`.

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
    ) -> None:
        """Construct the beets session and stash the async-bridge handles used by the decision hooks."""
        # beets stores paths as bytes; `ImportSession.__init__(lib, loghandler, paths, query)`.
        super().__init__(library, None, [bytestring_path(p) for p in paths], None)
        self._job_id = job_id
        self._portal = portal
        self._bridge = bridge
        self._store = store
        self._output = output
        self._quiet = quiet

    # beets interactive hooks below execute in beets' pipeline threads, not the event loop.

    def choose_match(self, task: Any) -> Any:
        """Ask the UI which candidate to apply for an album `task` (or to skip / import as-is)."""
        album_label = f"{getattr(task, 'cur_artist', '?')} - {getattr(task, 'cur_album', '?')}"
        if self._portal.call(self._store.is_abort_requested, self._job_id):
            self._output.append(f"Skipping '{album_label}' (abort requested).")
            return Action.SKIP

        if self._quiet:
            # Non-interactive (`beet import -q`): decide without prompting the UI.
            return self._quiet_choice(task, album_label)

        request = self._build_decision_request(task)
        self._output.append(f"Matching '{album_label}' — {len(request.candidates)} candidate(s); awaiting decision.")
        # Blocks THIS beets thread until the UI answers (the portal runs `bridge.request` on the loop).
        decision = self._portal.call(self._bridge.request, request)

        if decision.action is ImportAction.SKIP:
            self._output.append(f"Skipped '{album_label}'.")
            return Action.SKIP
        if decision.action is ImportAction.ASIS:
            self._output.append(f"Importing '{album_label}' as-is (tags unchanged).")
            return Action.ASIS
        # TODO[Claude]: validate `candidate_index` against `task.candidates`; handle empty/None.
        index = decision.candidate_index or 0
        chosen = request.candidates[index].label if index < len(request.candidates) else f"#{index}"
        match = task.candidates[index]
        self._output.append(f"Applying candidate '{chosen}' to '{album_label}':")
        for line in _build_album_diff(task, match):
            self._output.append(line)
        return match

    def _quiet_choice(self, task: Any, album_label: str) -> Any:
        """Decide a match without prompting (the `beet import -q` rule).

        Apply the best candidate iff beets rates the match a *strong* recommendation; otherwise fall back to
        beets' `import.quiet_fallback` config (skip by default, or import as-is).
        """
        # Imported here (not at module load) to keep beets internals lazy, like the rest of `core`.
        from beets.autotag import Recommendation

        candidates = getattr(task, "candidates", None) or []
        if candidates and getattr(task, "rec", None) is Recommendation.strong:
            match = candidates[0]  # beets sorts candidates best-first
            self._output.append(f"Quiet import: applying strong match for '{album_label}':")
            for line in _build_album_diff(task, match):
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

    def resolve_duplicate(self, task: Any, found_duplicates: Any) -> None:
        """Decide what to do when an import duplicates existing library entries."""
        # TODO[Claude]: bridge a duplicate-resolution DecisionRequest (keep both / remove old / skip).
        #     Scaffold default is the safe choice: skip the duplicate import.
        _LOGGER.warning("resolve_duplicate not yet implemented for job %s; skipping duplicate.", self._job_id)
        self._output.append("Duplicate of an existing library entry detected — skipping it.")
        task.set_choice(Action.SKIP)

    def should_resume(self, path: Any) -> bool:
        """Whether to resume a previously-interrupted import for `path` (scaffold: never)."""
        # TODO[Claude]: surface resume as a decision instead of always declining.
        return False

    def _build_decision_request(self, task: Any) -> DecisionRequest:
        """Map a beets album `task` and its candidates into a serializable `DecisionRequest`.

        Each candidate carries the differentiating release attributes from beets' `AlbumInfo` (year,
        country, media, label/catalognum, disambiguation, track count, source + id) so the UI can tell
        otherwise-identical candidates apart. All attribute access is defensive (beets-internal objects).
        """
        candidates = []
        for index, match in enumerate(getattr(task, "candidates", [])):
            info = getattr(match, "info", None)
            label = f"{getattr(info, 'artist', '?')} - {getattr(info, 'album', '?')}"
            distance = getattr(match, "distance", None)
            similarity = (1.0 - float(distance)) if distance is not None else None
            tracks = getattr(info, "tracks", None)
            candidates.append(
                ImportCandidate(
                    index=index,
                    label=label,
                    similarity=similarity,
                    data_source=getattr(info, "data_source", None) or None,
                    year=getattr(info, "year", None) or None,
                    country=getattr(info, "country", None) or None,
                    media=getattr(info, "media", None) or None,
                    record_label=getattr(info, "label", None) or None,
                    catalognum=getattr(info, "catalognum", None) or None,
                    disambiguation=getattr(info, "albumdisambig", None) or None,
                    track_count=len(tracks) if tracks else None,
                    album_id=getattr(info, "album_id", None) or None,
                )
            )
        return DecisionRequest(
            job_id=self._job_id,
            task_id=str(id(task)),
            prompt="Choose a match for this album.",
            candidates=candidates,
            allowed_actions=[ImportAction.APPLY, ImportAction.ASIS, ImportAction.SKIP],
        )


class ImportWorker:
    """Per-process import runner; only the lease holder actually runs imports (see module docstring).

    Launch `run()` as a background task in the FastAPI lifespan. Submit/answer/abort/status all go through
    the shared `ImportStore` (not this object), so they work no matter which process handles the request.
    """

    def __init__(self, beets_config_filepath: Path, store: ImportStore) -> None:
        """Create the worker over the shared store; mint a unique-per-process worker id."""
        self._beets_config_filepath = beets_config_filepath
        self._store = store
        self._bridge = DecisionBridge(store)
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._was_leader = False

    async def run(self) -> None:
        """Leader loop: acquire/renew the lease, recover orphans on election, then claim + run jobs."""
        await self._store.ensure_lock_row()
        async with BlockingPortal() as portal:
            while True:
                if not await self._store.acquire_lock(self._worker_id, _LEASE_SECONDS):
                    self._was_leader = False
                    await anyio.sleep(_IDLE_POLL)
                    continue
                if not self._was_leader:
                    self._was_leader = True
                    recovered = await self._store.recover_orphans(self._worker_id)
                    if recovered:
                        _LOGGER.warning("Failed %d orphaned import job(s) on becoming import leader.", recovered)
                job = await self._store.claim_next(self._worker_id)
                if job is None:
                    await anyio.sleep(_IDLE_POLL)
                    continue
                await self._run_job(job, portal)

    async def _run_job(self, job: ImportJob, portal: BlockingPortal) -> None:
        output = _OutputBuffer()
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self._renew_lease_until_cancelled)
            # Flush the growing output to the DB so any process polling the job renders progress live.
            task_group.start_soon(self._flush_output_until_cancelled, job.id, output)
            try:
                # Run the multi-threaded beets pipeline on one worker thread; the lease is renewed
                # concurrently so we keep leadership across long imports / decision waits.
                imported = await to_thread.run_sync(self._run_import_blocking, job, portal, output)
                aborted = await self._store.is_abort_requested(job.id)
                if not aborted:
                    # Record what we imported so the events page reflects beetkeeper's own imports (the
                    # external listener plugin only covers imports run outside beetkeeper).
                    await self._store.record_import_events(imported)
                output.append("Import aborted." if aborted else "Import completed.")
                await self._store.set_output(job.id, output.snapshot()[1])  # final flush before terminal status
                await self._store.set_status(job.id, ImportJobStatus.ABORTED if aborted else ImportJobStatus.COMPLETED)
            except Exception as exc:  # keep the worker alive; record the failure on the job
                _LOGGER.exception("Import job %s failed.", job.id)
                output.append(f"Import failed: {exc}")
                await self._store.set_output(job.id, output.snapshot()[1])
                await self._store.set_status(job.id, ImportJobStatus.FAILED, error=str(exc))
            finally:
                task_group.cancel_scope.cancel()

    async def _renew_lease_until_cancelled(self) -> None:
        while True:
            await anyio.sleep(_RENEW_INTERVAL)
            await self._store.acquire_lock(self._worker_id, _LEASE_SECONDS)

    async def _flush_output_until_cancelled(self, job_id: str, output: _OutputBuffer) -> None:
        """Persist the job's output to the DB whenever it grows (so pollers see incremental progress)."""
        last_version = -1
        while True:
            await anyio.sleep(_OUTPUT_FLUSH_INTERVAL)
            version, text = output.snapshot()
            if version != last_version:
                last_version = version
                await self._store.set_output(job_id, text)

    def _run_import_blocking(self, job: ImportJob, portal: BlockingPortal, output: _OutputBuffer) -> ImportedEntities:
        """Open the library, run the beets import to completion, and report what it added.

        Executes in a worker thread (beets connections are thread-local). The added albums/items are found
        by diffing the library's ids before and after the run — beetkeeper doesn't load beets plugins, so
        there is no in-pipeline event hook to capture them. beets warnings/errors during the run are funneled
        into `output` alongside the session's own narrative lines.
        """
        output.append(f"Starting import of: {', '.join(job.paths)}")
        handler = _BufferLogHandler(output)
        handler.setLevel(logging.WARNING)  # only surface beets warnings/errors; our hooks emit the narrative
        handler.setFormatter(logging.Formatter("beets %(levelname)s: %(message)s"))
        beets_logger = logging.getLogger("beets")
        beets_logger.addHandler(handler)
        try:
            library = open_library(self._beets_config_filepath)
            if (warning := _metadata_source_warning()) is not None:
                output.append(warning)
            existing_album_ids = {album.id for album in library.albums()}
            existing_item_ids = {item.id for item in library.items()}
            session = WebImportSession(
                library,
                job.paths,
                job_id=job.id,
                portal=portal,
                bridge=self._bridge,
                store=self._store,
                output=output,
                quiet=job.quiet,
            )
            session.run()  # blocks until beets' pipeline finishes (or drains via cooperative SKIP on abort)
            return self._collect_imported(library, existing_album_ids, existing_item_ids, output)
        finally:
            beets_logger.removeHandler(handler)

    @staticmethod
    def _collect_imported(
        library: Any, existing_album_ids: set[int], existing_item_ids: set[int], output: _OutputBuffer
    ) -> ImportedEntities:
        """Diff the post-import library against the pre-import id snapshots; record what was added in `output`."""
        albums: list[ImportedAlbum] = []
        for album in library.albums():
            if album.id in existing_album_ids:
                continue
            item_ids = [item.id for item in album.items()]
            albums.append(ImportedAlbum(album_id=album.id, item_ids=item_ids))
            label = f"{getattr(album, 'albumartist', '') or '?'} - {getattr(album, 'album', '') or '?'}"
            output.append(f"Imported album: {label} ({len(item_ids)} track(s)).")
        albumed_item_ids = {item_id for album in albums for item_id in album.item_ids}
        singleton_item_ids = [
            item.id for item in library.items() if item.id not in existing_item_ids and item.id not in albumed_item_ids
        ]
        for item_id in singleton_item_ids:
            output.append(f"Imported standalone track (item id {item_id}).")
        if not albums and not singleton_item_ids:
            output.append("No new items were added to the library.")
        return ImportedEntities(albums=albums, singleton_item_ids=singleton_item_ids)
