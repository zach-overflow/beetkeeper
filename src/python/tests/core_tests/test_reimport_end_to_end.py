"""End-to-end library reimports: the real beets pipeline over a throwaway library, in library (`-L`) mode.

`ImportWorker._run_import_blocking` runs an actual `WebImportSession` here. The beets config turns autotag
off (every task is imported as-is, so no metadata source or network is involved) and threading off (the
pipeline runs in the calling thread). The audio "files" are empty: nothing in this flow reads their contents.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from beets.library import Item, Library
from pytest_mock import MockerFixture

from beetkeeper.core import ImportStore
from beetkeeper.core.import_jobs import ImportJob, ImportJobStatus
from beetkeeper.core.import_worker import ImportWorker, _OutputBuffer
from beetkeeper.core.reimport_diff import ReimportDiffCollector


@pytest.fixture(autouse=True)
def restore_beets_config() -> Iterator[None]:
    """Drop every config source these tests add (the temp config file + per-job overrides) afterwards."""
    from beets import config

    config["import"]["copy"].get()  # materialize the lazy config so `sources` is populated
    original_sources = list(config.sources)
    try:
        yield
    finally:
        config.sources[:] = original_sources


@pytest.fixture
def beets_config_file(tmp_path: Path) -> Path:
    config_file = tmp_path / "beets.yaml"
    config_file.write_text(
        f"library: {tmp_path}/lib.db\n"
        f"directory: {tmp_path}/music\n"
        "plugins: []\n"
        "threaded: no\n"
        "import:\n"
        "  autotag: no\n"
        "  copy: yes\n"
        "  write: no\n",
        encoding="utf-8",
    )
    return config_file


def _add_album(library: Library, directory: Path, album: str, titles: list[str]) -> list[Path]:
    directory.mkdir(parents=True)
    paths = [directory / f"{title}.mp3" for title in titles]
    items = []
    for track, (title, path) in enumerate(zip(titles, paths, strict=True), start=1):
        path.touch()
        items.append(
            Item(artist="Artist", albumartist="Artist", album=album, title=title, track=track, path=str(path).encode())
        )
    library.add_album(items)
    return paths


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))


def _reimport(mocker: MockerFixture, beets_config_file: Path, **job_fields: Any) -> tuple[str, ReimportDiffCollector]:
    job = ImportJob(id="job-1", status=ImportJobStatus.RUNNING, paths=[], created_at=datetime.now(UTC), **job_fields)
    output = _OutputBuffer()
    collector = ReimportDiffCollector(output.append)
    worker = ImportWorker(beets_config_file, mocker.MagicMock(spec=ImportStore))
    worker._run_import_blocking(job, mocker.MagicMock(spec=BlockingPortal), output, collector)
    return output.snapshot()[1], collector


def test_reimport_in_place_reports_the_diff_and_leaves_files_alone(
    mocker: MockerFixture, tmp_path: Path, beets_config_file: Path, library: Library
) -> None:
    from beets import config

    paths = _add_album(library, tmp_path / "music" / "unsorted", "Album", ["One", "Two"])
    _add_album(library, tmp_path / "music" / "other", "Untouched", ["Other"])

    text, collector = _reimport(
        mocker, beets_config_file, query=["album:Album"], move_files=False, set_fields={"mood": "calm"}
    )

    assert "Starting reimport of library albums matching: album:Album" in text
    assert "Reimported album: Artist - Album (2 track(s))." in text
    (entry,) = collector.report().entries
    assert entry.label == "Artist - Album"
    assert [(change.field, change.new) for change in entry.shared_changes] == [("mood", "calm")]

    assert all(path.exists() for path in paths)
    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    assert sorted(item.path.decode() for item in reopened.items("album:Album")) == sorted(map(str, paths))
    assert {item.get("mood") for item in reopened.items("album:Album")} == {"calm"}
    assert {item.get("mood") for item in reopened.items("album:Untouched")} == {None}
    assert len(reopened.albums()) == 2

    # The job's overrides (and beets' own implied config edits) stayed on the session's detached copy.
    assert config["import"]["copy"].get(bool) is True
    assert config["import"]["singletons"].get(bool) is False
    assert config["import"]["incremental"].get(bool) is False


def test_reimport_moves_files_to_match_their_tags(
    mocker: MockerFixture, tmp_path: Path, beets_config_file: Path, library: Library
) -> None:
    (old_path,) = _add_album(library, tmp_path / "music" / "unsorted", "Album", ["One"])

    _text, collector = _reimport(mocker, beets_config_file, query=[], move_files=True)

    assert not old_path.exists()
    (new_path,) = (tmp_path / "music" / "Artist" / "Album").iterdir()
    (entry,) = collector.report().entries
    assert [(change.field, change.old, change.new) for change in entry.tracks[0].changes] == [
        ("path", str(old_path), str(new_path))
    ]


def test_reimport_skips_an_album_whose_file_is_gone(
    mocker: MockerFixture, tmp_path: Path, beets_config_file: Path, library: Library
) -> None:
    (gone,) = _add_album(library, tmp_path / "music" / "broken", "Broken", ["Lost"])
    _add_album(library, tmp_path / "music" / "fine", "Fine", ["Kept"])
    gone.unlink()

    text, collector = _reimport(mocker, beets_config_file, query=[], move_files=True)

    report = collector.report()
    assert [(missing.label, missing.paths) for missing in report.missing_files] == [("Artist - Broken", [str(gone)])]
    assert [entry.label for entry in report.entries] == ["Artist - Fine"]
    assert "Skipping 'Artist - Broken'" in text
    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    assert [item.path.decode() for item in reopened.items("album:Broken")] == [str(gone)]


def test_singleton_reimport_only_touches_standalone_tracks(
    mocker: MockerFixture, tmp_path: Path, beets_config_file: Path, library: Library
) -> None:
    _add_album(library, tmp_path / "music" / "album", "Album", ["Album Track"])
    standalone = tmp_path / "music" / "standalone.mp3"
    standalone.touch()
    library.add(Item(artist="Artist", title="Standalone", path=str(standalone).encode()))

    text, collector = _reimport(mocker, beets_config_file, query=[], singletons=True, move_files=False)

    assert "Starting reimport of library singleton tracks matching: (entire library)" in text
    assert "Skipping 'Artist - Album Track': it belongs to an album" in text
    assert [entry.label for entry in collector.report().entries] == ["Artist - Standalone"]
    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    assert len(reopened.albums()) == 1
    assert len(list(reopened.albums()[0].items())) == 1
