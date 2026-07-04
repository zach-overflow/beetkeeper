"""Tests for `load_config`: beetkeeper settings come from the beets config's optional `beetkeeper` section."""

from pathlib import Path

import pytest

from beetkeeper.settings import UserConfig, load_config
from beetkeeper.settings.user_config import BeetKeeperConfigError

_BEETS_PREAMBLE = "directory: /music\nlibrary: /lib.db\n"
_BEETKEEPER_SECTION = """\
beetkeeper:
  log_level: DEBUG
  server:
    hostname: 0.0.0.0
    port: 9999
    server_workers: 3
  database:
    sqlite_path: /var/lib/beetkeeper/bk.db
"""


def _write_config(tmp_path: Path, body: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_loads_settings_from_beetkeeper_section(tmp_path: Path) -> None:
    """Settings are read from the `beetkeeper` section; the config path becomes `beets_config_filepath`."""
    config_path = _write_config(tmp_path, _BEETS_PREAMBLE + _BEETKEEPER_SECTION)
    config = load_config(config_path)
    assert isinstance(config, UserConfig)
    assert config.log_level == "DEBUG"
    assert config.server.hostname == "0.0.0.0"
    assert config.server.port == 9999
    assert config.server.server_workers == 3
    assert config.database.sqlite_path == Path("/var/lib/beetkeeper/bk.db")
    assert config.beets_config_filepath == config_path.resolve()


def test_beets_config_filepath_is_the_loaded_path_overriding_any_in_section(tmp_path: Path) -> None:
    """A stray `beets_config_filepath` inside the section is ignored in favor of the loaded config path."""
    body = _BEETS_PREAMBLE + _BEETKEEPER_SECTION + "  beets_config_filepath: /nonexistent/bogus.yaml\n"
    config_path = _write_config(tmp_path, body)
    assert load_config(config_path).beets_config_filepath == config_path.resolve()


def test_missing_beetkeeper_section_raises(tmp_path: Path) -> None:
    """The `beetkeeper` key is optional for beets, but beetkeeper needs its settings -> config error."""
    config_path = _write_config(tmp_path, _BEETS_PREAMBLE)
    with pytest.raises(BeetKeeperConfigError):
        load_config(config_path)


def test_non_mapping_beetkeeper_section_raises(tmp_path: Path) -> None:
    """A `beetkeeper` key that is not a mapping is rejected with a clear error."""
    config_path = _write_config(tmp_path, _BEETS_PREAMBLE + "beetkeeper: not-a-mapping\n")
    with pytest.raises(BeetKeeperConfigError):
        load_config(config_path)


def test_missing_config_file_raises(tmp_path: Path) -> None:
    """A nonexistent config path raises rather than crashing."""
    with pytest.raises(BeetKeeperConfigError):
        load_config(tmp_path / "does_not_exist.yaml")
