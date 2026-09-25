"""Unit tests for the clean-slate dry run (`core.clean_slate.preview`) and the file-health helpers.

These build a real temporary beets `Library` over small real WAV files (see `make_tagged_wav`), so the checks
against the filesystem — which files exist, what the source folder holds — are the genuine article. No beets
importer runs and nothing is removed here; that is `test_clean_slate_remove.py` / the end-to-end tests.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from beets.library import Album, Item, Library

from beetkeeper.core.clean_slate import (
    AlbumFileHealth,
    CleanSlateError,
    expected_tracks,
    file_health,
    preview,
    require_ok,
    saved_id,
)
from beetkeeper.core.import_jobs import CleanSlatePreview, CleanSlateTarget
from tests.conftest import TaggedWavWriter


def _album_items(
    make_tagged_wav: TaggedWavWriter,
    directory: Path,
    titles: Sequence[str],
    *,
    missing: Sequence[str] = (),
    album: str = "Album",
    artist: str = "Artist",
) -> list[Item]:
    """Items for an album whose files live in `directory`; those named in `missing` get a row but no file."""
    items = []
    for track, title in enumerate(titles, start=1):
        path = directory / f"{track:02d} {title}.wav"
        tags: dict[str, Any] = dict(
            title=title, artist=artist, albumartist=artist, album=album, track=track, tracktotal=len(titles)
        )
        if title in missing:
            items.append(Item(path=str(path).encode(), **tags))
        else:
            items.append(Item.from_path(make_tagged_wav(path, **tags)))
    return items


def _add_album(library: Library, items: list[Item]) -> Album:
    album = library.add_album(items)
    assert album.id is not None
    return album


def _source_folder(
    make_tagged_wav: TaggedWavWriter, directory: Path, titles: Sequence[str], *, album: str = "Album"
) -> Path:
    for track, title in enumerate(titles, start=1):
        make_tagged_wav(
            directory / f"{track:02d} {title}.wav",
            title=title,
            artist="Artist",
            albumartist="Artist",
            album=album,
            track=track,
            tracktotal=len(titles),
        )
    return directory


def _preview(
    library: Library, target: CleanSlateTarget, source: Path, downloads: Path, **kwargs: Any
) -> CleanSlatePreview:
    return preview(library, target, str(source), downloads_path=downloads, **kwargs)


def test_preview_reports_counts_deletions_and_lost_attributes(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    album_dir = tmp_path / "music" / "Artist" / "Album"
    items = _album_items(make_tagged_wav, album_dir, ["One", "Two", "Three"], missing=["Three"])
    album = _add_album(library, items)
    art = album_dir / "cover.jpg"
    art.write_bytes(b"jpg")
    album.artpath = str(art).encode()
    album.mood = "calm"
    album.store()
    items[0].rating = 5
    items[0].store()
    source = _source_folder(make_tagged_wav, downloads / "Artist - Album", ["One", "Two", "Three"])

    result = _preview(library, CleanSlateTarget("album", saved_id(album)), source, downloads)

    assert result.ok is True and result.errors == [] and result.warnings == []
    assert (result.label, result.item_count, result.files_present, result.files_missing) == ("Artist - Album", 3, 2, 1)
    assert result.missing_paths == [str(album_dir / "03 Three.wav")]
    assert result.expected_tracks == 3
    assert result.files_to_delete == [str(album_dir / "01 One.wav"), str(album_dir / "02 Two.wav")]
    assert result.files_kept_outside_library == []
    assert result.art_to_delete == str(art)
    assert result.flexible_attributes_lost == ["mood", "rating"]
    assert (result.source_path, result.source_audio_files, result.source_album_groups) == (str(source), 3, 1)


def test_preview_reports_preserved_fields_and_leaves_them_out_of_the_lost_ones(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    """Preserved values come from the album first, else the first item holding one; fixed fields never qualify."""
    items = _album_items(make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One", "Two"])
    album = _add_album(library, items)
    album.mood = "calm"
    album.torrent_hash = "abcdefg12345678"
    album.store()
    items[0].rating = 5
    items[0].store()
    items[1].foo = "some-value"
    items[1].store()
    source = _source_folder(make_tagged_wav, downloads / "Artist - Album", ["One", "Two"])

    result = _preview(
        library,
        CleanSlateTarget("album", saved_id(album)),
        source,
        downloads,
        preserve_fields=("torrent_hash", "foo", "rating", "absent", "album"),
    )

    assert result.fields_preserved == {"torrent_hash": "abcdefg12345678", "foo": "some-value", "rating": "5"}
    assert result.flexible_attributes_lost == ["mood"]
    assert result.ok is True


def test_preview_preserves_a_standalone_tracks_own_fields(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    item = Item.from_path(make_tagged_wav(tmp_path / "music" / "solo.wav", title="Solo", artist="Artist"))
    library.add(item)
    item.torrent_hash = "abcdefg12345678"
    item.store()
    source = make_tagged_wav(downloads / "solo.wav", title="Solo", artist="Artist")

    result = _preview(
        library, CleanSlateTarget("track", saved_id(item)), source, downloads, preserve_fields=("torrent_hash",)
    )

    assert result.fields_preserved == {"torrent_hash": "abcdefg12345678"}
    assert result.flexible_attributes_lost == [] and result.ok is True


def test_preview_unknown_entry_raises_not_found(library: Library, downloads: Path) -> None:
    with pytest.raises(CleanSlateError) as excinfo:
        _preview(library, CleanSlateTarget("album", 42), downloads / "x", downloads)
    assert excinfo.value.kind == "not_found"
    with pytest.raises(CleanSlateError) as excinfo:
        _preview(library, CleanSlateTarget("track", 42), downloads / "x", downloads)
    assert excinfo.value.kind == "not_found"


@pytest.mark.parametrize(
    ("source_setup", "expected_error"),
    [
        pytest.param(lambda downloads, tmp, wav: downloads / "nope", "does not exist", id="missing-source"),
        pytest.param(lambda downloads, tmp, wav: downloads, "must be a folder inside", id="downloads-root-itself"),
        pytest.param(
            lambda downloads, tmp, wav: _source_folder(wav, tmp / "elsewhere" / "Album", ["One"]),
            "must be a folder inside",
            id="outside-downloads",
        ),
        pytest.param(
            lambda downloads, tmp, wav: _source_folder(wav, tmp / "music" / "Artist" / "Album2", ["One"]),
            "inside the beets library directory",
            id="inside-library",
        ),
        pytest.param(
            lambda downloads, tmp, wav: _text_only(downloads / "notes"), "No readable audio files", id="no-audio"
        ),
        pytest.param(
            lambda downloads, tmp, wav: _two_albums(wav, downloads / "discography"),
            "holds 2 album folders",
            id="two-album-folders",
        ),
        pytest.param(
            lambda downloads, tmp, wav: wav(downloads / "single.wav", title="Single", artist="Artist"),
            "must be a folder for an album",
            id="file-for-an-album",
        ),
    ],
)
def test_preview_blocks_bad_sources(
    library: Library,
    downloads: Path,
    tmp_path: Path,
    make_tagged_wav: TaggedWavWriter,
    source_setup: object,
    expected_error: str,
) -> None:
    album = _add_album(library, _album_items(make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"]))
    source = source_setup(downloads, tmp_path, make_tagged_wav)  # type: ignore[operator]

    result = _preview(library, CleanSlateTarget("album", saved_id(album)), source, downloads)

    assert result.ok is False
    assert any(expected_error in error for error in result.errors), result.errors
    with pytest.raises(CleanSlateError) as excinfo:
        require_ok(result)
    assert excinfo.value.kind == "invalid" and excinfo.value.preview is result


def _text_only(directory: Path) -> Path:
    directory.mkdir(parents=True)
    (directory / "readme.txt").write_text("not audio", encoding="utf-8")
    return directory


def _two_albums(make_tagged_wav: TaggedWavWriter, directory: Path) -> Path:
    _source_folder(make_tagged_wav, directory / "Album A", ["One"], album="Album A")
    _source_folder(make_tagged_wav, directory / "Album B", ["One"], album="Album B")
    return directory


def test_preview_needs_confirmation_when_the_source_has_fewer_files(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    album = _add_album(
        library, _album_items(make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One", "Two", "Three"])
    )
    source = _source_folder(make_tagged_wav, downloads / "Artist - Album", ["One", "Two"])
    target = CleanSlateTarget("album", saved_id(album))

    result = _preview(library, target, source, downloads)
    assert result.errors == [] and result.needs_confirmation is True and result.ok is False
    assert any("delete files the source cannot replace" in warning for warning in result.warnings)
    with pytest.raises(CleanSlateError) as excinfo:
        require_ok(result)
    assert excinfo.value.kind == "needs_confirmation"

    confirmed = _preview(library, target, source, downloads, allow_fewer_files=True)
    assert confirmed.needs_confirmation is False and confirmed.ok is True
    assert confirmed.warnings == result.warnings  # the warning stays; only the gate is lifted
    require_ok(confirmed)


def test_preview_warns_when_nothing_is_missing_and_the_source_is_short_of_the_release(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    items = _album_items(make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One", "Two"])
    for item in items:
        item.tracktotal = 3
    album = _add_album(library, items)
    source = _source_folder(make_tagged_wav, downloads / "Artist - Album", ["One", "Two"])

    result = _preview(library, CleanSlateTarget("album", saved_id(album)), source, downloads)

    assert result.ok is True and result.expected_tracks == 3
    assert [warning[:40] for warning in result.warnings] == [
        "Every file of this entry is still on dis",
        "The source has 2 audio file(s) but the a",
    ]


def test_preview_warns_when_the_source_tags_name_a_different_album(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    album = _add_album(
        library, _album_items(make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"], missing=["One"])
    )
    source = _source_folder(make_tagged_wav, downloads / "Artist - Other", ["One"], album="Other")

    result = _preview(library, CleanSlateTarget("album", saved_id(album)), source, downloads)

    assert result.ok is True
    assert result.warnings == ["The source files are tagged 'Artist - Other'; the library entry is 'Artist - Album'."]


def test_preview_refuses_a_track_that_belongs_to_an_album(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    items = _album_items(make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"])
    album = _add_album(library, items)
    source = make_tagged_wav(downloads / "one.wav", title="One", artist="Artist")

    result = _preview(library, CleanSlateTarget("track", saved_id(items[0])), source, downloads)

    assert result.subject == "track" and result.label == "Artist - One"
    assert result.errors == [f"This track belongs to album #{album.id}; run the clean slate on that album instead."]


def test_preview_standalone_track_needs_exactly_one_source_file(
    library: Library, downloads: Path, tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    item = Item.from_path(make_tagged_wav(tmp_path / "music" / "solo.wav", title="Solo", artist="Artist"))
    library.add(item)
    target = CleanSlateTarget("track", saved_id(item))

    single_file = make_tagged_wav(downloads / "solo.wav", title="Solo", artist="Artist")
    result = _preview(library, target, single_file, downloads)
    assert result.ok is True and result.expected_tracks is None
    assert (result.item_count, result.files_present, result.source_audio_files) == (1, 1, 1)
    assert result.files_to_delete == [str(tmp_path / "music" / "solo.wav")]

    two_files = _source_folder(make_tagged_wav, downloads / "pair", ["A", "B"])
    result = _preview(library, target, two_files, downloads)
    assert result.errors == [f"'{two_files}' holds 2 audio files; a standalone track needs exactly one."]


def test_preview_never_plans_to_delete_files_outside_the_library_or_under_the_source(
    library: Library, downloads: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    """An in-place library (files left where they were downloaded) keeps every file: only rows go."""
    source = _source_folder(make_tagged_wav, downloads / "Artist - Album", ["One", "Two"])
    album = _add_album(library, [Item.from_path(path) for path in sorted(source.glob("*.wav"))])

    result = _preview(library, CleanSlateTarget("album", saved_id(album)), source, downloads)

    assert result.ok is True
    assert result.files_to_delete == [] and result.art_to_delete is None
    assert result.files_kept_outside_library == [str(source / "01 One.wav"), str(source / "02 Two.wav")]


def test_clean_slate_target_from_ids_needs_exactly_one_id() -> None:
    assert CleanSlateTarget.from_ids(3, None) == CleanSlateTarget("album", 3)
    assert CleanSlateTarget.from_ids(None, 4) == CleanSlateTarget("track", 4)
    for album_id, item_id in ((None, None), (1, 2)):
        with pytest.raises(ValueError, match="Exactly one"):
            CleanSlateTarget.from_ids(album_id, item_id)


def test_file_health_counts_missing_files_and_tracks_short_of_the_release(
    tmp_path: Path, make_tagged_wav: TaggedWavWriter
) -> None:
    items = _album_items(make_tagged_wav, tmp_path / "music" / "A" / "B", ["One", "Two", "Three"], missing=["Two"])
    for item in items:
        item.tracktotal = 4

    health = file_health(items)

    assert health == AlbumFileHealth(item_count=3, files_present=2, expected_tracks=4)
    assert (health.files_missing, health.short_of_release, health.incomplete) == (1, 1, True)
    assert file_health([]) == AlbumFileHealth(item_count=0, files_present=0, expected_tracks=None)
    assert file_health([]).incomplete is False


def test_expected_tracks_sums_per_disc_when_beets_numbers_per_disc() -> None:
    from beets import config

    discs = [
        Item(disc=1, disctotal=2, tracktotal=5, path=b"/m/1.wav"),
        Item(disc=1, disctotal=2, tracktotal=5, path=b"/m/2.wav"),
        Item(disc=2, disctotal=2, tracktotal=3, path=b"/m/3.wav"),
    ]
    original = config["per_disc_numbering"].get()
    try:
        config["per_disc_numbering"] = True
        assert expected_tracks(discs) == 8
        config["per_disc_numbering"] = False
        assert expected_tracks(discs) == 5
    finally:
        config["per_disc_numbering"] = original
    assert expected_tracks([Item(tracktotal=0, path=b"/m/x.wav")]) is None
