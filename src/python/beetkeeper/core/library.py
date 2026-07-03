"""
beets library adapter — opens the user's beets `Library` and runs *one-shot* operations
(query / modify / remove / stats) off the event loop.

Integration model (decided): beetkeeper drives beets **in-process via its Python API**, NOT by shelling
out to the `beet` CLI. beetkeeper and beets are co-located (same container/node), so they share the
filesystem and the beets library SQLite DB. In-process access avoids per-call interpreter+plugin startup,
yields structured objects instead of parsed stdout, and is the only clean way to drive the *interactive*
importer (see `beetkeeper.core.import_worker`).

beets' internal API is NOT a stable public contract, so ALL beets access is confined to this `core`
package (keep `beets` imports out of the `api` layer) and beets is version-pinned in
`src/python/pyproject.toml`.

beets dev docs: https://beets.readthedocs.io/en/v2.12.0/dev/

Concurrency:
  * The beets library is SQLite (single writer) and the app runs multiple uvicorn workers, so every
    *mutating* beets call is serialized app-wide through `library_write_limiter` (a `CapacityLimiter(1)`,
    also shared by the import worker). Reads are not serialized.
  * All blocking beets calls are pushed off the event loop with `anyio.to_thread.run_sync`.
  * beets opens thread-local SQLite connections, so a `Library` is opened *inside* the worker thread that
    uses it (we open per operation here; caching is a future optimization).
  * beets' plugin registry is process-global, so the configured plugins are loaded once (guarded by a lock)
    on the first `open_library` and shared thereafter (see `_load_plugins_once`).
"""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, TypeVar

from anyio import CapacityLimiter, to_thread

_LOGGER = logging.getLogger(__name__)

# App-wide serialization point for every mutating beets operation (import worker shares this).
library_write_limiter: Final[CapacityLimiter] = CapacityLimiter(1)

# beets' plugin registry is process-global (not per-`Library`), so plugins are loaded exactly once per
# process and shared by every `open_library`. This lock guards that one-time load against the concurrent
# worker threads that open libraries; the flag lives in a dict so it can be mutated without `global` (the
# `_loaded` key is flipped in place — see the concurrency notes in the module docstring).
_plugins_lock = threading.Lock()
_plugins_state: dict[str, bool] = {"loaded": False}

_T = TypeVar("_T")


def _load_plugins_once(beets_config: Any) -> None:
    """Load the plugins listed in the (already-set) beets config, exactly once per process.

    beets' `load_plugins()` reads the global config itself, instantiates each plugin — registering its
    event listeners (e.g. the importer's `album_imported`/`item_imported` hooks), DB field types, and
    queries — and fires the `pluginload` event. Because the registry is process-global, the first config
    opened determines the loaded plugin set for the lifetime of the process (one beets config per
    beetkeeper process, so this is fine). Loading a plugin does not itself perform network I/O;
    network-backed autotag plugins (e.g. musicbrainz/discogs) only reach out during an import's tagging
    stage. beets' own `load_plugins()` is idempotent, but we still guard with a lock for thread-safety.
    """
    if _plugins_state["loaded"]:
        return
    # Imported lazily (like the rest of beets here) so importing this module stays cheap.
    from beets import plugins

    with _plugins_lock:
        if _plugins_state["loaded"]:  # another thread won the race while we waited on the lock
            return
        plugin_names = list(beets_config["plugins"].as_str_seq())
        plugins.load_plugins()  # reads the global config set just above; instantiates + fires 'pluginload'
        _plugins_state["loaded"] = True
        if plugin_names:
            _LOGGER.info("Loaded beets plugins: %s", ", ".join(plugin_names))


def _jsonify(model: Any) -> dict[str, Any]:
    """Convert a beets `Item`/`Album` to a JSON-safe dict (bytes fields like `path`/`artpath` are decoded)."""
    return {
        key: (value.decode("utf-8", "replace") if isinstance(value, bytes) else value)
        for key, value in dict(model).items()
    }


def open_library(beets_config_filepath: Path) -> Any:
    """Load the user's beets config and return an open `beets.library.Library`.

    Performs blocking I/O (opens the SQLite DB); call only from a worker thread, never the event loop.
    """
    # Imported lazily so merely importing this module doesn't pull in (heavy) beets internals.
    from beets import config as beets_config
    from beets.library import Library

    # Point beets' confuse config at the user's file, load the plugins it lists (once per process, before
    # opening the Library so plugin-provided field types/queries are registered), then open the Library at
    # the configured db path + music directory.
    beets_config.set_file(str(beets_config_filepath))
    _load_plugins_once(beets_config)
    db_path = beets_config["library"].as_filename()
    directory = beets_config["directory"].as_filename()
    return Library(db_path, directory)


class BeetsLibrary:
    """Async facade over a beets `Library` for one-shot operations.

    Each call opens the library inside a worker thread (beets connections are thread-local) and runs off
    the event loop. Mutating calls additionally hold `library_write_limiter`. Read results are returned as
    JSON-safe dicts (see `_jsonify`). Queries are beets query *parts* (a list of tokens like the CLI args);
    beets parses them — fields (`artist:Beatles`), keywords, phrases, path queries, and trailing sort
    tokens (`year+`): https://beets.readthedocs.io/en/v2.12.0/reference/query.html
    """

    def __init__(self, beets_config_filepath: Path) -> None:
        """Bind the adapter to the beets config the library is opened from."""
        self._beets_config_filepath = beets_config_filepath

    async def _read(self, work: Callable[[Any], _T]) -> _T:
        def _do() -> _T:
            library = open_library(self._beets_config_filepath)
            return work(library)

        return await to_thread.run_sync(_do)

    async def _write(self, work: Callable[[Any], _T]) -> _T:
        async with library_write_limiter:
            return await self._read(work)

    async def query_items(self, query: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Return JSON-safe dicts for beets `Item`s matching the query parts (None/empty -> all items)."""
        parts = list(query) if query else None
        return await self._read(lambda lib: [_jsonify(item) for item in lib.items(parts)])

    async def query_albums(self, query: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Return JSON-safe dicts for beets `Album`s matching the query parts (None/empty -> all albums)."""
        parts = list(query) if query else None
        return await self._read(lambda lib: [_jsonify(album) for album in lib.albums(parts)])

    async def stats(self, query: Sequence[str] | None = None) -> dict[str, Any]:
        """Summary statistics over matching items, mirroring `beet stats` (size is approximate, no disk I/O)."""
        parts = list(query) if query else None

        def _do(lib: Any) -> dict[str, Any]:
            total_size = 0
            total_time_seconds = 0.0
            tracks = 0
            artists: set[str] = set()
            albums: set[int] = set()
            album_artists: set[str] = set()
            for item in lib.items(parts):
                total_size += int(item.length * item.bitrate / 8)  # approximate (matches `beet stats`)
                total_time_seconds += item.length
                tracks += 1
                artists.add(item.artist)
                album_artists.add(item.albumartist)
                if item.album_id:
                    albums.add(item.album_id)
            return {
                "tracks": tracks,
                "total_time_minutes": total_time_seconds / 60.0,
                "approximate_total_size_bytes": total_size,
                "artists": len(artists),
                "albums": len(albums),
                "album_artists": len(album_artists),
            }

        return await self._read(_do)

    async def fields(self) -> dict[str, list[str]]:
        """Available item/album query fields + flexible attributes, mirroring `beet fields`."""

        def _do(lib: Any) -> dict[str, list[str]]:
            from beets.library import Album, Item

            with lib.transaction() as tx:
                # inline bandit ignores: table names are trusted beets class constants (not user input), and SQL
                # identifiers can't be parameter-bound. No injection vector.
                # NOTE: Cannot use individual bandit error codes here because it will give erroneous, unsuppressable warnings  (see https://github.com/PyCQA/bandit/issues/942)
                item_flex = [row["key"] for row in tx.query(f"SELECT DISTINCT key FROM {Item._flex_table}")]  # nosec
                album_flex = [row["key"] for row in tx.query(f"SELECT DISTINCT key FROM {Album._flex_table}")]  # nosec
            return {
                "item_fields": sorted(Item.all_keys()),
                "album_fields": sorted(Album.all_keys()),
                "item_flexible_attributes": sorted(item_flex),
                "album_flexible_attributes": sorted(album_flex),
            }

        return await self._read(_do)

    async def modify_items(self, query: str, changes: Mapping[str, str], *, write_tags: bool = True) -> int:
        """Apply field `changes` to every item matching `query`; return the number modified."""

        def _do(lib: Any) -> int:
            # TODO[Claude]: confirm beets API — set fields per item, optionally `item.try_write()`, then
            #     `item.store()` / `lib.save()`. Parse/typed-coerce values like `beet modify` does.
            count = 0
            for item in lib.items(query):
                for field, value in changes.items():
                    item[field] = value
                if write_tags:
                    item.try_write()
                item.store()
                count += 1
            return count

        return await self._write(_do)

    async def remove_items(self, query: str, *, delete_files: bool = False) -> int:
        """Remove items matching `query` from the library; return the number removed.

        With `delete_files=True` the underlying media files are deleted from disk too.
        """

        def _do(lib: Any) -> int:
            # TODO[Claude]: confirm beets API — `item.remove(delete=delete_files)` per matched item.
            count = 0
            for item in lib.items(query):
                item.remove(delete=delete_files)
                count += 1
            return count

        return await self._write(_do)
