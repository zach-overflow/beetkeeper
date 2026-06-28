"""Tests for the import-time hint warning when no beets metadata-source plugin is enabled.

These manipulate the process-global beets plugin registry directly (set the config's `plugins`, clear the
caches, reload), mirroring how `open_library` loads plugins — no network or real autotagging involved.
"""

from collections.abc import Iterator

import pytest

from beetkeeper.core.import_worker import _metadata_source_warning


def _reload_plugins(plugin_names: list[str]) -> None:
    """Set beets' configured plugin list and (re)load it, clearing the relevant caches first."""
    from beets import config, metadata_plugins, plugins

    config["plugins"] = plugin_names
    plugins._instances.clear()
    metadata_plugins.find_metadata_source_plugins.cache_clear()
    plugins.load_plugins()


@pytest.fixture
def restore_beets_plugins() -> Iterator[None]:
    """Reset the global beets plugin state after each test so cases don't leak into one another."""
    from beets import config

    autotag_was = config["import"]["autotag"].get(bool)
    try:
        yield
    finally:
        config["import"]["autotag"] = autotag_was
        _reload_plugins([])


@pytest.mark.usefixtures("restore_beets_plugins")
def test_warns_when_autotag_on_and_no_metadata_sources() -> None:
    from beets import config

    config["import"]["autotag"] = True
    _reload_plugins(["fetchart", "scrub"])  # neither is a metadata source

    warning = _metadata_source_warning()
    assert warning is not None
    assert "no metadata-source plugins are enabled" in warning
    assert "musicbrainz" in warning


@pytest.mark.usefixtures("restore_beets_plugins")
def test_no_warning_when_a_metadata_source_is_enabled() -> None:
    from beets import config

    config["import"]["autotag"] = True
    _reload_plugins(["musicbrainz", "fetchart"])

    assert _metadata_source_warning() is None


@pytest.mark.usefixtures("restore_beets_plugins")
def test_no_warning_when_autotag_is_off() -> None:
    from beets import config

    config["import"]["autotag"] = False
    _reload_plugins([])  # no sources, but autotag is off so candidates aren't expected anyway

    assert _metadata_source_warning() is None
