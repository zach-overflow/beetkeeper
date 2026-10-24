"""Tests that `ImportSubmitRequest` defaults resolve lazily from beets' (process-global) `import` config.

The shared `beets_import_config` fixture (this package's `conftest.py`) mutates the global config view and
restores the touched keys, mirroring how `core_tests/test_metadata_source_warning.py` handles beets' global
state. No network or real import runs.
"""

from pathlib import Path
from typing import Any

import pytest

from beetkeeper.api.api_models import ImportSubmitRequest

_FLAG_KEYS = ("quiet", "group_albums", "flat")


@pytest.mark.parametrize("enabled", [True, False])
def test_flag_defaults_follow_beets_config(beets_import_config: Any, enabled: bool) -> None:
    for key in _FLAG_KEYS:
        beets_import_config[key] = enabled
    request = ImportSubmitRequest(paths=["/music/in"])
    assert request.quiet is enabled
    assert request.group_albums is enabled
    assert request.flat is enabled


def test_set_fields_default_follows_beets_config(beets_import_config: Any) -> None:
    beets_import_config["set_fields"] = {"genre": "Jazz", "year": 1999}
    request = ImportSubmitRequest(paths=["/music/in"])
    assert request.set_fields == {"genre": "Jazz", "year": "1999"}


def test_logpath_defaults_to_configured_import_log(beets_import_config: Any, tmp_path: Path) -> None:
    beets_import_config["log"] = str(tmp_path / "import.log")
    assert ImportSubmitRequest(paths=["/music/in"]).logpath == tmp_path / "import.log"


def test_unconfigured_defaults_match_beets_shipped_defaults(beets_import_config: Any) -> None:
    request = ImportSubmitRequest(paths=["/music/in"])
    assert request.quiet is False
    assert request.logpath is None
    assert request.group_albums is False
    assert request.flat is False
    assert request.set_fields == {}


def test_explicit_values_override_beets_config(beets_import_config: Any, tmp_path: Path) -> None:
    beets_import_config["quiet"] = True
    beets_import_config["flat"] = True
    beets_import_config["log"] = str(tmp_path / "configured.log")
    request = ImportSubmitRequest(
        paths=["/music/in"], quiet=False, flat=False, logpath=tmp_path / "explicit.log", set_fields={"genre": "Jazz"}
    )
    assert request.quiet is False
    assert request.flat is False
    assert request.logpath == tmp_path / "explicit.log"
    assert request.set_fields == {"genre": "Jazz"}
