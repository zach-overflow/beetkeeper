"""Tests for the candidate-chooser table model (`build_candidate_table`).

Columns are the union of attributes that *differ* across candidates; the Apply button is added by the
template as the trailing cell, so it isn't part of this model.
"""

from beetkeeper.api.ui_routes.import_ui_fragments_router import build_candidate_table
from beetkeeper.core import ImportCandidate


def _candidate(index: int, **attrs: object) -> ImportCandidate:
    return ImportCandidate(index=index, label="Boards of Canada - Inferno", **attrs)


def test_no_candidates_returns_none() -> None:
    assert build_candidate_table([]) is None


def test_columns_are_only_the_differing_attributes() -> None:
    candidates = [
        _candidate(
            0,
            similarity=0.99,
            data_source="MusicBrainz",
            year=2026,
            media="Digital Media",
            catalognum="W1",
            album_id="id0",
        ),
        _candidate(
            1, similarity=0.99, data_source="MusicBrainz", year=2007, media="CD", catalognum="W2", album_id="id1"
        ),
        _candidate(
            2, similarity=0.90, data_source="MusicBrainz", year=2007, media="CD", catalognum="W3", album_id="id2"
        ),
    ]

    table = build_candidate_table(candidates)
    assert table is not None
    # label (same), data_source (same), country/label/disambig/tracks (all None) are excluded.
    # similarity, year, media, catalognum differ; album_id differs -> "Link" via release_url.
    assert table["headers"] == ["Match", "Year", "Media", "Catalog #", "Link"]
    assert [row["index"] for row in table["rows"]] == [0, 1, 2]

    first = table["rows"][0]
    assert [cell["text"] for cell in first["cells"]] == ["99%", "2026", "Digital Media", "W1", "view"]
    assert first["cells"][-1]["url"] == "https://musicbrainz.org/release/id0"  # the Link cell


def test_attribute_shared_by_all_candidates_is_hidden() -> None:
    candidates = [
        _candidate(0, similarity=0.99, year=2007, media="CD"),
        _candidate(1, similarity=0.90, year=2007, media="Vinyl"),
    ]
    table = build_candidate_table(candidates)
    assert table is not None
    assert "Year" not in table["headers"]  # both 2007 -> not differentiating
    assert table["headers"] == ["Match", "Media"]


def test_single_candidate_shows_all_populated_attributes() -> None:
    table = build_candidate_table([_candidate(0, similarity=0.97, year=2026, media="Digital Media")])
    assert table is not None
    # Nothing to differentiate against, so each populated attribute is shown.
    assert table["headers"] == ["Match", "Album", "Year", "Media"]
    assert len(table["rows"]) == 1


def test_link_column_hidden_when_no_release_urls() -> None:
    # Differing album_ids but a non-MusicBrainz source yields no release_url, so the Link column is dropped.
    candidates = [
        _candidate(0, similarity=0.9, data_source="Discogs", album_id="d0"),
        _candidate(1, similarity=0.8, data_source="Discogs", album_id="d1"),
    ]
    table = build_candidate_table(candidates)
    assert table is not None
    assert table["headers"] == ["Match"]  # album_id differs but release_url is None for both
