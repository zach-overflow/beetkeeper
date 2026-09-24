"""Unit tests for `beetkeeper.core.reimport_diff`: snapshot diffing and the collector's task guards.

Items are real (database-less) beets `Item`s, so the snapshot exercises beets' own field access; tasks are
attribute stand-ins, since the collector only reads `is_album`/`items`/`item`/`skip`/`imported_items()`.
"""

from pathlib import Path
from typing import Any

import pytest
from beets.library import Item

from beetkeeper.core.import_jobs import FieldChange
from beetkeeper.core.reimport_diff import MAX_REPORT_ENTRIES, ReimportDiffCollector, diff_snapshots, item_snapshot


class _Task:
    """Minimal stand-in for a beets `ImportTask`/`SingletonImportTask`."""

    def __init__(self, items: list[Item], *, is_album: bool = True, imported: list[Item] | None = None) -> None:
        self.is_album = is_album
        self.items = items
        self.item = items[0] if items else None
        self.skip = False
        self._imported = items if imported is None else imported

    def imported_items(self) -> list[Item]:
        return self._imported


def _item(tmp_path: Path, name: str, *, exists: bool = True, **fields: Any) -> Item:
    path = tmp_path / name
    if exists:
        path.touch()
    defaults: dict[str, Any] = {"artist": "Artist", "albumartist": "Artist", "album": "Album", "title": name}
    return Item(path=str(path).encode(), **(defaults | fields))


@pytest.fixture
def narration() -> list[str]:
    return []


@pytest.fixture
def collector(narration: list[str]) -> ReimportDiffCollector:
    return ReimportDiffCollector(narration.append)


def test_item_snapshot_decodes_paths_and_skips_bookkeeping_fields(tmp_path: Path) -> None:
    snapshot = item_snapshot(_item(tmp_path, "a.mp3", mood="calm"))

    assert snapshot["path"] == str(tmp_path / "a.mp3")
    assert snapshot["mood"] == "calm"
    assert not {"id", "album_id", "mtime", "added"} & snapshot.keys()


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        pytest.param({"genre": "Jazz"}, {"genre": "Jazz"}, [], id="unchanged"),
        pytest.param({"year": "0000"}, {"year": None}, [], id="blank-to-blank-is-not-a-change"),
        pytest.param({"comp": "False"}, {"comp": ""}, [], id="false-is-blank"),
        pytest.param(
            {"title": "trk"}, {"title": "Track"}, [FieldChange(field="title", old="trk", new="Track")], id="changed"
        ),
        pytest.param({}, {"label": "Warp"}, [FieldChange(field="label", old=None, new="Warp")], id="added"),
        pytest.param({"genre": "Jazz"}, {"genre": ""}, [FieldChange(field="genre", old="Jazz", new="")], id="dropped"),
    ],
)
def test_diff_snapshots(old: dict[str, str | None], new: dict[str, str | None], expected: list[FieldChange]) -> None:
    assert diff_snapshots(old, new) == expected


@pytest.mark.parametrize(
    ("old", "new", "dropped"),
    [("Jazz", "", True), ("Jazz", None, True), ("1998", "0000", True), ("Jazz", "Rock", False), (None, "Rock", False)],
)
def test_field_change_flags_lost_values(old: str | None, new: str | None, dropped: bool) -> None:
    assert FieldChange(field="f", old=old, new=new).dropped is dropped


def test_album_level_changes_are_hoisted_out_of_the_tracks(
    tmp_path: Path, collector: ReimportDiffCollector, narration: list[str]
) -> None:
    one, two = _item(tmp_path, "1.mp3", mood="calm"), _item(tmp_path, "2.mp3", mood="calm")
    task = _Task([one, two])
    assert collector.task_created(task) is None

    for item in (one, two):
        item.album = "Album (Remastered)"
        item.mood = ""
    one.title = "One"
    collector.task_files(task)

    (entry,) = collector.report().entries
    assert entry.label == "Artist - Album"
    assert [(change.field, change.dropped) for change in entry.shared_changes] == [("album", False), ("mood", True)]
    assert [[change.field for change in track.changes] for track in entry.tracks] == [["title"], []]
    assert "3 field change(s), 1 of which lost their previous value" in narration[-1]


def test_tracks_the_match_did_not_cover_are_reported_as_left_behind(
    tmp_path: Path, collector: ReimportDiffCollector
) -> None:
    kept, unmatched = _item(tmp_path, "1.mp3", title="Kept"), _item(tmp_path, "2.mp3", title="Bonus")
    task = _Task([kept, unmatched], imported=[kept])
    collector.task_created(task)
    collector.task_files(task)

    (entry,) = collector.report().entries
    assert entry.left_behind == ["Artist - Bonus"]
    assert [track.label for track in entry.tracks] == ["Artist - Kept"]


def test_task_with_a_missing_file_is_dropped_and_reported(
    tmp_path: Path, collector: ReimportDiffCollector, narration: list[str]
) -> None:
    task = _Task([_item(tmp_path, "here.mp3"), _item(tmp_path, "gone.mp3", exists=False)])

    assert collector.task_created(task) == []
    collector.task_files(task)

    report = collector.report()
    assert report.entries == []
    assert [(missing.label, missing.paths) for missing in report.missing_files] == [
        ("Artist - Album", [str(tmp_path / "gone.mp3")])
    ]
    assert "1 of 2 file(s) no longer exist on disk" in narration[0]


def test_singleton_reimport_skips_a_track_that_belongs_to_an_album(
    tmp_path: Path, collector: ReimportDiffCollector, narration: list[str]
) -> None:
    album_track = _item(tmp_path, "a.mp3", album_id=7)
    standalone = _item(tmp_path, "b.mp3")

    assert collector.task_created(_Task([album_track], is_album=False)) == []
    assert collector.task_created(_Task([standalone], is_album=False)) is None
    assert "would detach it" in narration[0]


def test_skipped_task_yields_no_entry(tmp_path: Path, collector: ReimportDiffCollector) -> None:
    task = _Task([_item(tmp_path, "1.mp3")])
    collector.task_created(task)
    task.skip = True
    collector.task_choice(task)
    collector.task_files(task)

    assert collector.report().entries == []


def test_report_is_capped(tmp_path: Path, collector: ReimportDiffCollector) -> None:
    item = _item(tmp_path, "1.mp3")
    for _ in range(MAX_REPORT_ENTRIES + 1):
        task = _Task([item])
        collector.task_created(task)
        collector.task_files(task)

    report = collector.report()
    assert len(report.entries) == MAX_REPORT_ENTRIES
    assert report.truncated is True
