"""Tests for event-based narration of what an import added.

The worker narrates imported albums/items through beets' own `album_imported`/`item_imported` events
(process-global `BeetsPlugin.listeners` registry). These tests dispatch through `beets.plugins.send` — the
same call path the importer pipeline uses — to prove the listener registration end-to-end, rather than
invoking the handlers directly. Albums/items are attribute stand-ins (see `_Attrs` in `test_import_diff`).
"""

from typing import Any

from beets import plugins

from beetkeeper.core.import_worker import _import_events, _ImportNarrator, _OutputBuffer


class _Attrs:
    """Minimal attribute bag standing in for beets `Album`/`Item` objects."""

    def __init__(self, **attrs: Any) -> None:
        self.__dict__.update(attrs)


def _album(album_id: int, item_ids: list[int]) -> _Attrs:
    items = [_Attrs(id=item_id) for item_id in item_ids]
    return _Attrs(id=album_id, albumartist="Artist", album="Album", items=lambda: items)


def test_send_routes_events_to_the_active_narrator_and_narrates_output() -> None:
    events = _import_events()
    output = _OutputBuffer()
    narrator = _ImportNarrator(output)
    events.narrator = narrator
    try:
        plugins.send("album_imported", lib=None, album=_album(7, [11, 12]))
        plugins.send("item_imported", lib=None, item=_Attrs(id=99, artist="Solo Artist", title="Solo Track"))
    finally:
        events.narrator = None

    assert narrator.imported_count == 2
    text = output.snapshot()[1]
    assert "Imported album: Artist - Album (2 track(s))." in text
    assert "Imported standalone track: Solo Artist - Solo Track." in text


def test_events_with_no_active_narrator_are_ignored() -> None:
    events = _import_events()
    assert events.narrator is None

    # Fires the registered listeners with no narrator installed (e.g. an import run by another beets
    # client in-process while the worker is idle); nothing should be narrated anywhere or raise.
    plugins.send("album_imported", lib=None, album=_album(1, [2]))
    plugins.send("item_imported", lib=None, item=_Attrs(id=3, artist="A", title="T"))

    assert events.narrator is None


def test_deactivated_narrator_stops_receiving_events() -> None:
    events = _import_events()
    narrator = _ImportNarrator(_OutputBuffer())
    events.narrator = narrator
    try:
        plugins.send("album_imported", lib=None, album=_album(5, [6]))
    finally:
        events.narrator = None
    plugins.send("album_imported", lib=None, album=_album(8, [9]))

    assert narrator.imported_count == 1


def test_import_events_returns_the_same_registered_instance() -> None:
    # The listener registry is append-only, so repeated lookups must reuse one instance (a second
    # instance would double-dispatch every event).
    assert _import_events() is _import_events()
