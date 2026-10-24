"""Tests for the destructive half of a clean slate (`core.clean_slate.remove_entry`) over a real temp library.

The library is populated with small real WAV files so the deletion rules are checked against the filesystem:
rows always go, files go only when they live inside the beets directory and not under the source path,
album art follows the same rule, and emptied directories are pruned.
"""

from pathlib import Path

import pytest
from beets.library import Album, Item, Library
from pytest_mock import MockerFixture

from beetkeeper.core.clean_slate import CleanSlateError, remove_entry, saved_id
from beetkeeper.core.import_jobs import CleanSlateTarget
from tests.conftest import TaggedWavWriter


def _album_with_files(
    library: Library, make_tagged_wav: TaggedWavWriter, directory: Path, titles: list[str], *, art: bool = False
) -> tuple[Album, list[Path]]:
    paths = [directory / f"{track:02d} {title}.wav" for track, title in enumerate(titles, start=1)]
    items = [
        Item.from_path(make_tagged_wav(path, title=title, artist="Artist", albumartist="Artist", album="Album"))
        for path, title in zip(paths, titles, strict=True)
    ]
    album = library.add_album(items)
    if art:
        cover = directory / "cover.jpg"
        cover.write_bytes(b"jpg")
        album.artpath = str(cover).encode()
        album.store()
    return album, paths


def test_remove_album_deletes_rows_library_files_and_art_and_prunes_empty_dirs(
    library: Library, tmp_path: Path, make_tagged_wav: TaggedWavWriter, mocker: MockerFixture
) -> None:
    album_dir = tmp_path / "music" / "Artist" / "Album"
    album, paths = _album_with_files(library, make_tagged_wav, album_dir, ["One", "Two"], art=True)
    (tmp_path / "music" / "Artist" / "Other" / "keep.txt").parent.mkdir()
    (tmp_path / "music" / "Artist" / "Other" / "keep.txt").write_text("x", encoding="utf-8")
    send = mocker.patch("beets.plugins.send")
    lines: list[str] = []

    removed = remove_entry(
        library, CleanSlateTarget("album", saved_id(album)), str(tmp_path / "downloads" / "src"), narrate=lines.append
    )

    assert removed.target == CleanSlateTarget("album", saved_id(album))
    assert removed.item_ids == [item.id for item in album.items()] or len(removed.item_ids) == 2
    assert removed.deleted_paths == [str(path) for path in paths]
    assert removed.kept_paths == [] and removed.deleted_art == str(album_dir / "cover.jpg")
    assert len(library.albums()) == 0 and len(library.items()) == 0
    assert not any(path.exists() for path in paths)
    assert not album_dir.exists(), "the emptied album folder is pruned"
    assert (tmp_path / "music" / "Artist" / "Other" / "keep.txt").exists(), "sibling content is untouched"
    assert (tmp_path / "music").exists(), "the library root is never pruned"
    assert lines == [
        f"Removed album 'Artist - Album' (#{album.id}) from the library: 2 row(s), 2 file(s) deleted, album art deleted."
    ]
    events = [call.args[0] for call in send.call_args_list]
    assert events.count("item_removed") == 2 and events.count("album_removed") == 1


def test_remove_keeps_files_outside_the_library_and_under_the_source(
    library: Library, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    """An in-place library entry (files still in the download folder): rows go, the files stay for the import."""
    source = tmp_path / "downloads" / "Artist - Album"
    album, paths = _album_with_files(library, make_tagged_wav, source, ["One", "Two"])
    lines: list[str] = []

    removed = remove_entry(library, CleanSlateTarget("album", saved_id(album)), str(source), narrate=lines.append)

    assert removed.deleted_paths == [] and removed.deleted_art is None
    assert removed.kept_paths == [str(path) for path in paths]
    assert all(path.exists() for path in paths)
    assert len(library.albums()) == 0 and len(library.items()) == 0
    assert lines[0].endswith("2 row(s), 0 file(s) deleted, 2 file(s) outside the library left alone.")


def test_remove_skips_deleting_files_that_are_already_gone(
    library: Library, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    album, paths = _album_with_files(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One", "Two"])
    paths[1].unlink()

    removed = remove_entry(
        library, CleanSlateTarget("album", saved_id(album)), str(tmp_path / "downloads"), narrate=lambda _: None
    )

    assert removed.deleted_paths == [str(paths[0])]
    assert len(library.items()) == 0


def test_remove_standalone_track(library: Library, tmp_path: Path, make_tagged_wav: TaggedWavWriter) -> None:
    path = make_tagged_wav(tmp_path / "music" / "solo.wav", title="Solo", artist="Artist")
    item = Item.from_path(path)
    library.add(item)
    lines: list[str] = []

    removed = remove_entry(
        library, CleanSlateTarget("track", saved_id(item)), str(tmp_path / "downloads"), narrate=lines.append
    )

    assert removed.item_ids == [item.id] and removed.deleted_paths == [str(path)]
    assert not path.exists() and len(library.items()) == 0
    assert lines == [f"Removed track 'Artist - Solo' (#{item.id}) from the library: 1 row(s), 1 file(s) deleted."]


def test_remove_unknown_entry_raises_not_found(library: Library, tmp_path: Path) -> None:
    with pytest.raises(CleanSlateError) as excinfo:
        remove_entry(library, CleanSlateTarget("album", 99), str(tmp_path), narrate=lambda _: None)
    assert excinfo.value.kind == "not_found"
