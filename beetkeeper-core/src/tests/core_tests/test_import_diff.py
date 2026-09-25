"""Unit tests for the verbose per-album diff rendered into an import job's output log.

`_build_album_diff` reads a beets `AlbumMatch`'s attributes defensively, so it can be exercised with plain
attribute stand-ins — no real beets autotagging (or network) required. The stand-in is a tiny identity-
hashable object (not `SimpleNamespace`, which is unhashable and so can't be a `mapping` dict key).
"""

from collections.abc import Callable, Sequence
from typing import Any

from beets.autotag import Recommendation
from beets.importer import Action

from beetkeeper.core.import_jobs import ImportAction, ImportCandidate, ImportDecision
from beetkeeper.core.import_worker import (
    WebImportSession,
    _build_album_diff,
    _build_track_diff,
    _OutputBuffer,
    _track_candidate,
)
from tests.core_tests.conftest import Attrs


class _FakePortal:
    """Stands in for an anyio `BlockingPortal`: `call()` returns queued results in order, ignoring the fn."""

    def __init__(self, results: Sequence[Any]) -> None:
        self._results = list(results)
        self._index = 0

    def call(self, _func: Callable[..., Any], *_args: Any) -> Any:
        result = self._results[self._index]
        self._index += 1
        return result


def test_album_diff_reports_album_track_and_unmatched_changes() -> None:
    task = Attrs(cur_artist="Old Artist", cur_album="Old Album")
    item_one = Attrs(title="track one", track=1)
    item_two = Attrs(title="trk 2", track=2)
    match = Attrs(
        info=Attrs(artist="New Artist", album="New Album", year=2007, data_source="MusicBrainz"),
        distance=0.1,
        mapping={item_one: Attrs(title="Track One", index=1), item_two: Attrs(title="Track Two", index=2)},
        extra_tracks=[Attrs(title="Bonus Track")],
        extra_items=[Attrs(title="weird file")],
    )

    text = "\n".join(_build_album_diff(task, match))

    assert "Match: New Artist - New Album (2007) [MusicBrainz] (90.0% match)" in text
    assert "Artist: Old Artist -> New Artist" in text
    assert "Album: Old Album -> New Album" in text
    assert "(track 1) track one -> Track One" in text
    assert "(track 2) trk 2 -> Track Two" in text
    assert "Missing track: Bonus Track" in text
    assert "Unmatched track: weird file" in text


def test_album_diff_track_changes_sorted_by_position() -> None:
    task = Attrs(cur_artist="A", cur_album="B")
    item_late = Attrs(title="z", track=9)
    item_early = Attrs(title="a", track=1)
    match = Attrs(
        info=Attrs(artist="A", album="B"),
        distance=0.0,
        # Insertion order is "late then early" to prove the diff re-sorts by track position.
        mapping={item_late: Attrs(title="Z", index=9), item_early: Attrs(title="A", index=1)},
        extra_tracks=[],
        extra_items=[],
    )

    lines = _build_album_diff(task, match)
    track_lines = [line for line in lines if "->" in line]

    assert track_lines == ["    (track 1) a -> A", "    (track 9) z -> Z"]
    assert not any(line.strip().startswith(("Artist:", "Album:")) for line in lines)


def test_album_diff_without_info_is_empty() -> None:
    assert _build_album_diff(Attrs(cur_artist="a", cur_album="b"), Attrs(info=None)) == []


def test_choose_match_apply_writes_diff_to_output() -> None:
    """On APPLY, `choose_match` should append the chosen candidate's verbose diff to the job output."""
    # Build the session without beets' real `__init__` (which needs a Library); inject the bridge handles.
    session = WebImportSession.__new__(WebImportSession)
    session._job_id = "job-1"
    session._output = _OutputBuffer()
    session._quiet = False
    # portal.call is invoked twice: the abort check (False), then the decision request (APPLY candidate 0).
    session._portal = _FakePortal([False, ImportDecision(action=ImportAction.APPLY, candidate_index=0)])  # type: ignore[assignment]
    session._bridge = Attrs(request=lambda _request: None)  # type: ignore[assignment]
    session._store = Attrs(is_abort_requested=lambda _job_id: None)  # type: ignore[assignment]

    item = Attrs(title="old title", track=1)
    candidate = Attrs(
        info=Attrs(artist="New Artist", album="New Album", year=2020, data_source="MusicBrainz"),
        distance=0.1,
        mapping={item: Attrs(title="New Title", index=1)},
        extra_tracks=[],
        extra_items=[],
    )
    task = Attrs(cur_artist="Old Artist", cur_album="Old Album", candidates=[candidate])

    result = session.choose_match(task)

    assert result is candidate
    output = session._output.snapshot()[1]
    assert "Applying candidate 'New Artist - New Album' to 'Old Artist - Old Album':" in output
    assert "Match: New Artist - New Album (2020) [MusicBrainz] (90.0% match)" in output
    assert "(track 1) old title -> New Title" in output


def test_candidate_details_joins_known_attributes() -> None:
    candidate = ImportCandidate(
        index=0,
        label="Boards of Canada - Inferno",
        similarity=0.99,
        data_source="MusicBrainz",
        year=2026,
        country="XW",
        media="Digital Media",
        record_label="Warp",
        catalognum="WARP123",
        disambiguation="WEB",
        track_count=12,
        album_id="abc-123",
        release_url="https://musicbrainz.org/release/abc-123",
    )
    assert candidate.details == "2026 · XW · Digital Media · Warp [WARP123] · 12 tracks · MusicBrainz · WEB"
    assert candidate.release_url == "https://musicbrainz.org/release/abc-123"


def test_candidate_details_empty_and_no_url_when_attributes_absent() -> None:
    candidate = ImportCandidate(index=0, label="A - B", similarity=0.5)
    assert candidate.details == ""
    assert candidate.release_url is None


def test_build_decision_request_populates_differentiating_details() -> None:
    session = WebImportSession.__new__(WebImportSession)
    session._job_id = "job-x"
    info = Attrs(
        artist="Boards of Canada",
        album="Inferno",
        year=2026,
        country="XW",
        media="Digital Media",
        label="Warp",
        catalognum="WARP123",
        albumdisambig="WEB",
        data_source="MusicBrainz",
        album_id="abc-123",
        data_url="https://musicbrainz.org/release/abc-123",
        tracks=[Attrs(), Attrs(), Attrs()],
    )
    task = Attrs(candidates=[Attrs(info=info, distance=0.01)])

    request = session._build_decision_request(task)
    candidate = request.candidates[0]

    assert candidate.label == "Boards of Canada - Inferno"
    assert (candidate.year, candidate.media, candidate.record_label) == (2026, "Digital Media", "Warp")
    assert candidate.catalognum == "WARP123" and candidate.track_count == 3
    assert "Warp [WARP123]" in candidate.details and "MusicBrainz" in candidate.details
    assert candidate.release_url == "https://musicbrainz.org/release/abc-123"


def test_build_decision_request_coerces_non_string_attributes() -> None:
    """Non-MusicBrainz sources may use non-string fields (e.g. Discogs' int release ids)."""
    session = WebImportSession.__new__(WebImportSession)
    session._job_id = "job-z"
    info = Attrs(
        artist="Butthole Surfers",
        album="After The Astronaut",
        year=2026,
        label="Sunset Blvd Records",
        catalognum=634457247475,
        data_source="Discogs",
        album_id=34097392,
        tracks=[],
    )
    task = Attrs(candidates=[Attrs(info=info, distance=0.02)])

    candidate = session._build_decision_request(task).candidates[0]

    assert candidate.album_id == "34097392"
    assert candidate.catalognum == "634457247475"
    assert candidate.record_label == "Sunset Blvd Records"
    assert candidate.release_url is None  # source provided no `data_url`


def test_build_decision_request_handles_sparse_candidate_info() -> None:
    session = WebImportSession.__new__(WebImportSession)
    session._job_id = "job-y"
    # Empty strings (beets' AlbumInfo defaults) should become None, not blank detail fragments.
    info = Attrs(artist="A", album="B", year=0, country="", media="", label="", catalognum="", tracks=[])
    task = Attrs(candidates=[Attrs(info=info, distance=0.2)])

    candidate = session._build_decision_request(task).candidates[0]

    assert candidate.label == "A - B"
    assert candidate.year is None and candidate.country is None and candidate.track_count is None
    assert candidate.details == ""


def _quiet_session() -> WebImportSession:
    """A `WebImportSession` set up for quiet mode (no real beets `__init__`); abort check returns False."""
    session = WebImportSession.__new__(WebImportSession)
    session._job_id = "job-q"
    session._output = _OutputBuffer()
    session._quiet = True
    session._portal = _FakePortal([False])  # type: ignore[assignment]
    session._store = Attrs(is_abort_requested=lambda _job_id: None)  # type: ignore[assignment]
    return session


def test_quiet_mode_applies_a_strong_match_without_prompting() -> None:
    session = _quiet_session()
    item = Attrs(title="old", track=1)
    candidate = Attrs(
        info=Attrs(artist="A", album="B"),
        distance=0.05,
        mapping={item: Attrs(title="New", index=1)},
        extra_tracks=[],
        extra_items=[],
    )
    task = Attrs(cur_artist="A", cur_album="B", candidates=[candidate], rec=Recommendation.strong)

    result = session.choose_match(task)

    assert result is candidate
    output = session._output.snapshot()[1]
    assert "Quiet import: applying strong match" in output
    assert "(track 1) old -> New" in output


def test_quiet_mode_skips_when_no_strong_match() -> None:
    session = _quiet_session()
    candidate = Attrs(info=Attrs(artist="A", album="B"), distance=0.6, mapping={}, extra_tracks=[], extra_items=[])
    task = Attrs(cur_artist="A", cur_album="B", candidates=[candidate], rec=Recommendation.none)

    result = session.choose_match(task)

    # Default `quiet_fallback` is "skip"; nothing is applied and no decision is ever requested.
    assert result is Action.SKIP
    assert "skipping" in session._output.snapshot()[1].lower()


def _singleton_session(portal_results: Sequence[Any], *, quiet: bool = False) -> WebImportSession:
    session = WebImportSession.__new__(WebImportSession)
    session._job_id = "job-1"
    session._output = _OutputBuffer()
    session._quiet = quiet
    session._portal = _FakePortal(portal_results)  # type: ignore[assignment]
    session._bridge = Attrs(request=lambda _request: None)  # type: ignore[assignment]
    session._store = Attrs(is_abort_requested=lambda _job_id: None)  # type: ignore[assignment]
    return session


def _track_candidate_match() -> Attrs:
    info = Attrs(
        artist="Burial", title="Archangel", data_source="MusicBrainz", track_id=1234, data_url="https://mb/track/1234"
    )
    return Attrs(info=info, distance=0.05)


def test_track_diff_reports_artist_and_title_changes() -> None:
    task = Attrs(item=Attrs(artist="burial", title="archangel"))

    assert _build_track_diff(task, _track_candidate_match()) == [
        "  Match: Burial - Archangel [MusicBrainz] (95.0% match)",
        "    Artist: burial -> Burial",
        "    Title: archangel -> Archangel",
    ]


def test_choose_item_builds_a_track_decision_and_applies_the_choice() -> None:
    """Singleton tasks (`-s`) park on the same decision flow as albums, with track-shaped candidates."""
    session = _singleton_session([False, ImportDecision(action=ImportAction.APPLY, candidate_index=0)])
    match = _track_candidate_match()
    task = Attrs(item=Attrs(artist="burial", title="archangel"), candidates=[match])

    request = session._build_decision_request(task, "Choose a match for this track.", _track_candidate)
    assert request.prompt == "Choose a match for this track."
    assert request.candidates == [
        ImportCandidate(
            index=0,
            label="Burial - Archangel",
            similarity=0.95,
            data_source="MusicBrainz",
            album_id="1234",
            release_url="https://mb/track/1234",
        )
    ]

    assert session.choose_item(task) is match
    output = session._output.snapshot()[1]
    assert "Applying candidate 'Burial - Archangel' to 'burial - archangel':" in output
    assert "Title: archangel -> Archangel" in output


def test_choose_item_quiet_applies_a_strong_match_with_the_track_diff() -> None:
    session = _singleton_session([False], quiet=True)
    match = _track_candidate_match()
    task = Attrs(item=Attrs(artist="burial", title="archangel"), candidates=[match], rec=Recommendation.strong)

    assert session.choose_item(task) is match
    assert "Artist: burial -> Burial" in session._output.snapshot()[1]


def test_choose_item_skip() -> None:
    session = _singleton_session([False, ImportDecision(action=ImportAction.SKIP)])
    task = Attrs(item=Attrs(artist="a", title="t"), candidates=[])

    assert session.choose_item(task) is Action.SKIP
    assert "Skipped 'a - t'." in session._output.snapshot()[1]
