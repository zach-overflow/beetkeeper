"""Tests for recording beets plugin load failures and surfacing them in import job output.

`_load_plugins_once` diffs the configured plugin list against what actually loaded (process-global beets
registry, restored by a fixture); `_failed_plugins_warning` turns the recorded failures into the hint line
every import job prepends. No network or real autotagging involved.
"""

from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

import beetkeeper.core.library as library_module
from beetkeeper.core.import_worker import _failed_plugins_warning
from beetkeeper.core.library import _load_plugins_once


@pytest.fixture
def fresh_plugin_state(mocker: MockerFixture) -> Iterator[None]:
    """Give the test its own (unloaded) plugin bookkeeping; restore beets' global plugin registry after."""
    from beets import config, metadata_plugins, plugins

    mocker.patch.object(library_module, "_plugins_state", {"loaded": False})
    mocker.patch.object(library_module, "_failed_plugin_names", [])
    original_plugins = list(config["plugins"].as_str_seq())
    plugins._instances.clear()  # beets' load_plugins() is a no-op while instances exist
    try:
        yield
    finally:
        config["plugins"] = original_plugins
        plugins._instances.clear()
        metadata_plugins.find_metadata_source_plugins.cache_clear()
        plugins.load_plugins()


@pytest.mark.usefixtures("fresh_plugin_state")
def test_missing_plugins_are_recorded() -> None:
    from beets import config

    config["plugins"] = ["fetchart", "not_a_real_plugin"]
    _load_plugins_once()

    assert library_module.failed_plugin_names() == ("not_a_real_plugin",)


@pytest.mark.usefixtures("fresh_plugin_state")
def test_no_failures_recorded_when_all_plugins_load() -> None:
    from beets import config

    config["plugins"] = ["fetchart"]
    _load_plugins_once()

    assert library_module.failed_plugin_names() == ()


@pytest.mark.usefixtures("fresh_plugin_state")
def test_disabled_plugins_are_not_reported_as_failures() -> None:
    from beets import config

    config["plugins"] = ["fetchart", "scrub"]
    config["disabled_plugins"] = ["scrub"]
    try:
        _load_plugins_once()
        assert library_module.failed_plugin_names() == ()
    finally:
        config["disabled_plugins"] = []


def test_failed_plugins_warning_lists_the_failed_names(mocker: MockerFixture) -> None:
    mocker.patch("beetkeeper.core.import_worker.failed_plugin_names", return_value=("originquery", "discogs"))

    warning = _failed_plugins_warning()
    assert warning is not None
    assert "2 configured beets plugin(s) failed to load" in warning
    assert "originquery, discogs" in warning


def test_failed_plugins_warning_is_none_without_failures(mocker: MockerFixture) -> None:
    mocker.patch("beetkeeper.core.import_worker.failed_plugin_names", return_value=())

    assert _failed_plugins_warning() is None
