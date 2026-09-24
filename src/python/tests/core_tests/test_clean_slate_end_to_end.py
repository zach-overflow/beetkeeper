"""End-to-end clean-slate imports: the real beets pipeline over a throwaway library and real WAV files.

`ImportWorker._run_import_blocking` runs an actual `WebImportSession` here, preceded by the clean-slate
removal. The beets config turns autotag off (every task is imported as-is, so no metadata source or network
is involved) and threading off (the pipeline runs in the calling thread). The audio files are tiny tagged
WAVs (see `make_tagged_wav`), which beets reads for real.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from beets.library import Album, Item, Library
from pytest_mock import MockerFixture
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.core import ImportStore
from beetkeeper.core.clean_slate import CleanSlateError, saved_id
from beetkeeper.core.import_jobs import ImportJob, ImportJobStatus
from beetkeeper.core.import_worker import ImportWorker, WebImportSession, _ImportRunResult, _OutputBuffer
from beetkeeper.core.library import _config_state, open_library
from beetkeeper.db.models import InferredSourcePath
from tests.conftest import TaggedWavWriter


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
        _config_state["file"] = None


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


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    path = tmp_path / "downloads"
    path.mkdir()
    return path


@pytest.fixture
def worker(beets_config_file: Path, downloads: Path, mocker: MockerFixture) -> ImportWorker:
    return ImportWorker(beets_config_file, mocker.MagicMock(spec=ImportStore), downloads)


def _tags(title: str, track: int, total: int, album: str = "Album") -> dict[str, Any]:
    return dict(title=title, artist="Artist", albumartist="Artist", album=album, track=track, tracktotal=total)


def _add_album(
    library: Library,
    make_tagged_wav: TaggedWavWriter,
    directory: Path,
    titles: list[str],
    *,
    missing: tuple[str, ...] = (),
    album: str = "Album",
) -> Album:
    items = []
    for track, title in enumerate(titles, start=1):
        path = directory / f"{track:02d} {title}.wav"
        tags = _tags(title, track, len(titles), album)
        if title in missing:
            items.append(Item(path=str(path).encode(), **tags))
        else:
            items.append(Item.from_path(make_tagged_wav(path, **tags)))
    return library.add_album(items)


def _source(make_tagged_wav: TaggedWavWriter, directory: Path, titles: list[str], album: str = "Album") -> Path:
    for track, title in enumerate(titles, start=1):
        make_tagged_wav(directory / f"{track:02d} {title}.wav", **_tags(title, track, len(titles), album))
    return directory


def _job(source: Path, **fields: Any) -> ImportJob:
    return ImportJob(
        id="job-1", status=ImportJobStatus.RUNNING, paths=[str(source)], created_at=datetime.now(UTC), **fields
    )


def _run(worker: ImportWorker, mocker: MockerFixture, job: ImportJob) -> tuple[str, _ImportRunResult]:
    output = _OutputBuffer()
    result = worker._run_import_blocking(job, mocker.MagicMock(spec=BlockingPortal), output)
    return output.snapshot()[1], result


def _wav_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.wav"))


def test_clean_slate_replaces_an_album_with_a_missing_file(
    worker: ImportWorker, mocker: MockerFixture, tmp_path: Path, library: Library, make_tagged_wav: TaggedWavWriter
) -> None:
    album_dir = tmp_path / "music" / "Artist" / "Album"
    old = _add_album(library, make_tagged_wav, album_dir, ["One", "Two", "Three"], missing=("Three",))
    old.mood = "calm"
    old.store()
    old_item_ids = [item.id for item in old.items()]
    source = _source(make_tagged_wav, tmp_path / "downloads" / "Artist - Album", ["One", "Two", "Three"])

    text, result = _run(worker, mocker, _job(source, clean_slate_album_id=old.id))

    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    (album,) = reopened.albums()
    assert sorted(item.title for item in album.items()) == ["One", "Three", "Two"]
    assert album.get("mood") is None, "a clean slate carries nothing over"
    library_files = _wav_files(tmp_path / "music")
    assert len(library_files) == 3 and not any(".1." in path.name for path in library_files)
    assert all(path.exists() for path in _wav_files(source)), "copy mode leaves the source alone"
    assert result.removed is not None and result.removed.item_ids == old_item_ids
    assert result.removed.deleted_paths == [str(album_dir / "01 One.wav"), str(album_dir / "02 Two.wav")]
    assert result.imported_album_ids == [album.id]
    assert "Starting clean-slate import of:" in text
    assert "3 library row(s), 2 file(s) on disk, 1 missing; the source folder holds 3 audio file(s)." in text
    assert "Flexible attributes not carried over: mood." in text
    assert f"Removed album 'Artist - Album' (#{old.id}) from the library: 3 row(s), 2 file(s) deleted." in text
    assert "Imported album: Artist - Album (3 track(s))." in text


def test_clean_slate_of_a_standalone_track_imports_a_singleton(
    worker: ImportWorker, mocker: MockerFixture, tmp_path: Path, library: Library, make_tagged_wav: TaggedWavWriter
) -> None:
    old_path = make_tagged_wav(tmp_path / "music" / "solo.wav", title="Solo", artist="Artist")
    old = Item.from_path(old_path)
    library.add(old)
    source = make_tagged_wav(tmp_path / "downloads" / "solo.wav", title="Solo", artist="Artist")

    text, result = _run(worker, mocker, _job(source, clean_slate_item_id=old.id))

    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    (item,) = reopened.items()
    assert item.album_id is None and item.title == "Solo"
    assert not old_path.exists() and source.exists()
    assert len(reopened.albums()) == 0
    assert result.removed is not None and result.removed.item_ids == [old.id]
    assert result.imported_item_ids == [item.id] and result.imported_album_ids == []
    assert "Imported standalone track: Artist - Solo." in text


def test_nothing_imported_leaves_the_entry_removed_and_says_so(
    worker: ImportWorker, mocker: MockerFixture, tmp_path: Path, library: Library, make_tagged_wav: TaggedWavWriter
) -> None:
    """A skipped/aborted import after the removal is a legitimate outcome; the narrative must spell it out."""
    old = _add_album(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"])
    source = _source(make_tagged_wav, tmp_path / "downloads" / "Artist - Album", ["One"])
    mocker.patch.object(WebImportSession, "run", return_value=None)

    text, result = _run(worker, mocker, _job(source, clean_slate_album_id=old.id))

    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    assert len(reopened.albums()) == 0 and _wav_files(tmp_path / "music") == []
    assert _wav_files(source) == [source / "01 One.wav"]
    assert result.removed is not None and result.imported_album_ids == []
    assert (
        f"Nothing was imported. The removed entry is gone from the library; its source files remain at {source}" in text
    )


@pytest.mark.parametrize(
    ("source_titles", "job_fields", "kind", "message"),
    [
        pytest.param(["One"], {}, "needs_confirmation", "fewer audio files", id="fewer-files-without-the-opt-in"),
        pytest.param([], {}, "invalid", "No readable audio files", id="empty-source"),
    ],
)
def test_guard_failures_touch_nothing(
    worker: ImportWorker,
    mocker: MockerFixture,
    tmp_path: Path,
    library: Library,
    make_tagged_wav: TaggedWavWriter,
    source_titles: list[str],
    job_fields: dict[str, Any],
    kind: str,
    message: str,
) -> None:
    old = _add_album(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One", "Two"])
    source = tmp_path / "downloads" / "Artist - Album"
    source.mkdir()
    _source(make_tagged_wav, source, source_titles)

    with pytest.raises(CleanSlateError, match=message) as excinfo:
        _run(worker, mocker, _job(source, clean_slate_album_id=old.id, **job_fields))

    assert excinfo.value.kind == kind
    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    assert [album.id for album in reopened.albums()] == [old.id]
    assert len(_wav_files(tmp_path / "music")) == 2


def test_source_inside_the_library_is_refused(
    worker: ImportWorker, mocker: MockerFixture, tmp_path: Path, library: Library, make_tagged_wav: TaggedWavWriter
) -> None:
    old = _add_album(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"])

    with pytest.raises(CleanSlateError, match="inside the beets library directory") as excinfo:
        _run(worker, mocker, _job(tmp_path / "music" / "Artist" / "Album", clean_slate_album_id=old.id))

    assert excinfo.value.kind == "invalid"
    assert len(_wav_files(tmp_path / "music")) == 1


def test_worker_without_a_downloads_path_refuses_clean_slates(
    beets_config_file: Path, mocker: MockerFixture, tmp_path: Path, library: Library, make_tagged_wav: TaggedWavWriter
) -> None:
    old = _add_album(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"])
    worker = ImportWorker(beets_config_file, mocker.MagicMock(spec=ImportStore))

    with pytest.raises(CleanSlateError, match="downloads_path"):
        _run(worker, mocker, _job(tmp_path / "downloads" / "x", clean_slate_album_id=old.id))


def test_a_same_named_other_album_is_left_alone(
    worker: ImportWorker, mocker: MockerFixture, tmp_path: Path, library: Library, make_tagged_wav: TaggedWavWriter
) -> None:
    """With the target gone, beets' duplicate check can only hit *other* albums; the default policy skips."""
    target = _add_album(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One"], missing=("One",))
    other = _add_album(library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album (other)", ["One", "Two"])
    source = _source(make_tagged_wav, tmp_path / "downloads" / "Artist - Album", ["One"])

    text, result = _run(worker, mocker, _job(source, clean_slate_album_id=target.id))

    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    assert [album.id for album in reopened.albums()] == [other.id]
    kept = reopened.get_album(saved_id(other))
    assert kept is not None and sorted(item.title for item in kept.items()) == ["One", "Two"]
    assert len(_wav_files(tmp_path / "music")) == 2
    assert result.imported_album_ids == []
    assert "duplicates an existing library entry — skipping the new import" in text


def test_incremental_history_does_not_skip_a_clean_slate_source(
    worker: ImportWorker,
    mocker: MockerFixture,
    tmp_path: Path,
    beets_config_file: Path,
    make_tagged_wav: TaggedWavWriter,
) -> None:
    """beets' incremental mode skips folders it imported before; a clean slate must re-import the source."""
    beets_config_file.write_text(
        beets_config_file.read_text(encoding="utf-8") + "  incremental: yes\n", encoding="utf-8"
    )
    source = _source(make_tagged_wav, tmp_path / "downloads" / "Artist - Album", ["One", "Two"])

    first, _ = _run(worker, mocker, _job(source))
    assert "Imported album: Artist - Album (2 track(s))." in first
    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    (album,) = reopened.albums()
    next(iter(_wav_files(tmp_path / "music"))).unlink()

    again, result = _run(worker, mocker, _job(source, clean_slate_album_id=album.id))

    assert result.imported_album_ids and "Imported album: Artist - Album (2 track(s))." in again
    assert len(_wav_files(tmp_path / "music")) == 2


def test_open_library_applies_the_config_file_once(beets_config_file: Path) -> None:
    from beets import config

    open_library(beets_config_file)
    sources_after_first = list(config.sources)
    open_library(beets_config_file)

    assert config.sources == sources_after_first


@pytest.mark.anyio
async def test_run_job_rekeys_the_inferred_source_path(
    beets_config_file: Path,
    downloads: Path,
    import_store: ImportStore,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    library: Library,
    make_tagged_wav: TaggedWavWriter,
) -> None:
    """The whole job path: the store row, the removal, the import, and the inference moving to the new id."""
    old = _add_album(
        library, make_tagged_wav, tmp_path / "music" / "Artist" / "Album", ["One", "Two"], missing=("Two",)
    )
    (old_item,) = [item for item in old.items() if item.title == "One"]
    source = _source(make_tagged_wav, downloads / "Artist - Album", ["One", "Two"])
    async with session_factory() as session:
        for subject, beets_id in (("album", saved_id(old)), ("track", saved_id(old_item))):
            session.add(
                InferredSourcePath(
                    subject_type=subject,
                    beets_id=beets_id,
                    source_path=str(source),
                    method="downloader_hook",
                    inferred_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
        await session.commit()
    job = await import_store.create([str(source)], clean_slate_album_id=old.id)
    claimed = await import_store.claim_next("worker-1")
    assert claimed is not None
    worker = ImportWorker(beets_config_file, import_store, downloads)

    async with BlockingPortal() as portal:
        await worker._run_job(claimed, portal)

    finished = await import_store.get(job.id)
    assert finished is not None and finished.status is ImportJobStatus.COMPLETED
    assert finished.output is not None and "Import completed." in finished.output
    reopened = Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))
    (album,) = reopened.albums()
    async with session_factory() as session:
        rows = (await session.execute(select(InferredSourcePath))).scalars().all()
    assert [(row.subject_type, row.beets_id, row.source_path) for row in rows] == [("album", album.id, str(source))]
