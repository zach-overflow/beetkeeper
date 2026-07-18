"""Tests for `_modify_matching_items` — the `beet modify`-equivalent core of `BeetsLibrary.modify_items`.

Runs against a real in-memory beets `Library` (no config file, plugins, or disk I/O: `write`/`move` stay
False so `try_sync` only stores to the DB), proving that string values are coerced into each field's beets
type via `Model.set_parse` rather than stored raw.
"""

from beets.library import Item, Library

from beetkeeper.core.library import _modify_matching_items


def _library_with_items(*items: Item) -> Library:
    library = Library(":memory:")
    for item in items:
        library.add(item)
    return library


def _single_item(library: Library, query: str) -> Item:
    item = library.items(query).get()
    assert item is not None
    return item


def test_values_are_parsed_into_field_types() -> None:
    library = _library_with_items(Item(title="old title", year=1999))

    count = _modify_matching_items(
        library, "title:old", {"year": "2026", "title": "new title"}, write=False, move=False
    )

    assert count == 1
    stored = _single_item(library, "title:new")
    assert stored.title == "new title"
    assert stored.year == 2026
    assert isinstance(stored.year, int)


def test_only_matching_items_are_modified() -> None:
    library = _library_with_items(Item(title="keep", year=1990), Item(title="change", year=1990))

    count = _modify_matching_items(library, "title:change", {"year": "2000"}, write=False, move=False)

    assert count == 1
    assert _single_item(library, "title:keep").year == 1990
    assert _single_item(library, "title:change").year == 2000


def test_no_matches_modifies_nothing() -> None:
    library = _library_with_items(Item(title="only", year=1990))

    assert _modify_matching_items(library, "title:absent", {"year": "2000"}, write=False, move=False) == 0
    assert _single_item(library, "title:only").year == 1990
