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


def test_auth_defaults_to_disabled_when_section_absent(tmp_path: Path) -> None:
    """No `auth` subsection means login protection is off (it is strictly opt-in)."""
    config_path = _write_config(tmp_path, _BEETS_PREAMBLE + _BEETKEEPER_SECTION)
    config = load_config(config_path)
    assert config.auth.enable_login_protection is False
    assert config.auth.username is None
    assert config.auth.password is None


def test_auth_section_parses_with_masked_credentials(tmp_path: Path) -> None:
    """Credentials load as `SecretStr` (masked in reprs/logs) alongside the enable flag and TTL."""
    body = (
        _BEETS_PREAMBLE
        + _BEETKEEPER_SECTION
        + "  auth:\n    enable_login_protection: true\n    username: admin\n    password: hunter2\n"
        + "    session_ttl_hours: 12\n"
    )
    config = load_config(_write_config(tmp_path, body))
    assert config.auth.enable_login_protection is True
    assert config.auth.username is not None and config.auth.username.get_secret_value() == "admin"
    assert config.auth.password is not None and config.auth.password.get_secret_value() == "hunter2"
    assert "hunter2" not in repr(config.auth)
    assert config.auth.session_ttl_hours == 12


def test_auth_enabled_without_credentials_raises(tmp_path: Path) -> None:
    """Turning on login protection without a username+password is a config error, caught at startup."""
    body = _BEETS_PREAMBLE + _BEETKEEPER_SECTION + "  auth:\n    enable_login_protection: true\n"
    with pytest.raises(BeetKeeperConfigError):
        load_config(_write_config(tmp_path, body))


def test_missing_beetkeeper_section_raises(tmp_path: Path) -> None:
    """The `beetkeeper` key is optional for beets, but beetkeeper needs its settings -> config error."""
    config_path = _write_config(tmp_path, _BEETS_PREAMBLE)
    with pytest.raises(BeetKeeperConfigError):
        load_config(config_path)


def test_missing_config_file_raises(tmp_path: Path) -> None:
    """A nonexistent config path raises rather than crashing."""
    with pytest.raises(BeetKeeperConfigError):
        load_config(tmp_path / "does_not_exist.yaml")
