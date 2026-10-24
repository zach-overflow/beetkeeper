"""Tests that `WebImportSession.get_duplicate_action` honors beets' `import.duplicate_action` config.

beets' pipeline calls `get_duplicate_action` when an import duplicates existing library entries; the web
session must return the configured action (with `ask` degrading to skip, as there is no interactive
duplicate prompt yet) and narrate the outcome in the job output.
"""

from collections.abc import Iterator

import pytest
from beets.importer import DuplicateAction
from pytest_mock import MockerFixture

from beetkeeper.core.import_worker import WebImportSession, _OutputBuffer


@pytest.fixture
def restore_duplicate_action() -> Iterator[None]:
    from beets import config

    original = config["import"]["duplicate_action"].get()
    try:
        yield
    finally:
        config["import"]["duplicate_action"] = original


def _session(mocker: MockerFixture) -> tuple[WebImportSession, _OutputBuffer]:
    output = _OutputBuffer()
    session = WebImportSession(
        None,
        ["/music/incoming"],
        job_id="job-1",
        portal=mocker.Mock(),
        bridge=mocker.Mock(),
        store=mocker.Mock(),
        output=output,
        quiet=True,
    )
    return session, output


@pytest.mark.usefixtures("restore_duplicate_action")
@pytest.mark.parametrize(
    ("configured", "expected", "narrative"),
    [
        ("skip", DuplicateAction.SKIP, "skipping the new import"),
        ("keep", DuplicateAction.KEEP, "keeping both"),
        ("remove", DuplicateAction.REMOVE, "replacing the existing entry"),
        ("merge", DuplicateAction.MERGE, "merging them"),
    ],
)
def test_configured_duplicate_action_is_honored(
    mocker: MockerFixture, configured: str, expected: DuplicateAction, narrative: str
) -> None:
    from beets import config

    config["import"]["duplicate_action"] = configured
    session, output = _session(mocker)
    task = mocker.Mock(cur_artist="Repro Artist", cur_album="Repro Album")

    assert session.get_duplicate_action(task, []) is expected
    text = output.snapshot()[1]
    assert "'Repro Artist - Repro Album' duplicates an existing library entry" in text
    assert narrative in text


@pytest.mark.usefixtures("restore_duplicate_action")
def test_singleton_tasks_without_album_metadata_get_placeholder_labels(mocker: MockerFixture) -> None:
    """beets leaves cur_artist/cur_album as None on singleton/asis tasks; the label must not say 'None'."""
    from beets import config

    config["import"]["duplicate_action"] = "skip"
    session, output = _session(mocker)
    task = mocker.Mock(cur_artist=None, cur_album=None)

    session.get_duplicate_action(task, [])
    assert "'? - ?' duplicates an existing library entry" in output.snapshot()[1]


@pytest.mark.usefixtures("restore_duplicate_action")
def test_ask_degrades_to_skip_with_an_explanation(mocker: MockerFixture) -> None:
    from beets import config

    config["import"]["duplicate_action"] = "ask"
    session, output = _session(mocker)
    task = mocker.Mock(cur_artist="A", cur_album="B")

    assert session.get_duplicate_action(task, []) is DuplicateAction.SKIP
    text = output.snapshot()[1]
    assert "skipping the new import" in text
    assert "'ask' is not supported in web imports yet" in text
