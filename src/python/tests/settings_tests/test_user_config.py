"""Tests for `load_config`: beetkeeper settings come from the beets config's optional `beetkeeper` section."""

import logging
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
    assert config.database.sqlite_path == Path("/var/lib/beetkeeper/bk.db")
    assert config.beets_config_filepath == config_path.resolve()


def test_removed_server_workers_key_is_ignored_with_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The removed `server.server_workers` key still loads (ignored) and emits a deprecation warning."""
    body = (_BEETS_PREAMBLE + _BEETKEEPER_SECTION).replace("port: 9999", "port: 9999\n    server_workers: 3")
    with caplog.at_level(logging.WARNING):
        config = load_config(_write_config(tmp_path, body))
    assert not hasattr(config.server, "server_workers")
    assert any("server_workers" in record.message for record in caplog.records)


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


def test_downloader_hook_is_disabled_by_default(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, _BEETS_PREAMBLE + _BEETKEEPER_SECTION))
    assert config.downloader_hook.enabled is False
    assert config.downloads_path == Path("/downloads")


def test_downloader_hook_section_is_loaded(tmp_path: Path) -> None:
    body = (
        _BEETS_PREAMBLE
        + _BEETKEEPER_SECTION
        + """\
  downloads_path: /mnt/downloads
  downloader_hook:
    base_url: http://qbit.local:8080
    search_endpoint_path: /api/v2/torrents/info
    beets_field_names_to_query_param_names:
      album: name
    filepath_json_key: content_path
    replace_downloader_paths_prefix: /data/torrents
    api_key: s3cret
"""
    )
    config = load_config(_write_config(tmp_path, body))
    hook = config.downloader_hook
    assert hook.enabled is True
    assert str(hook.base_url) == "http://qbit.local:8080/"
    assert hook.search_endpoint_path == "/api/v2/torrents/info"
    assert hook.beets_field_names_to_query_param_names == {"album": "name"}
    assert hook.filepath_json_key == "content_path"
    assert hook.replace_downloader_paths_prefix == "/data/torrents"
    assert hook.api_key is not None and hook.api_key.get_secret_value() == "s3cret"
    assert config.downloads_path == Path("/mnt/downloads")


@pytest.mark.parametrize(
    "omitted", ["search_endpoint_path", "filepath_json_key", "beets_field_names_to_query_param_names"]
)
def test_enabled_downloader_hook_requires_its_search_settings(tmp_path: Path, omitted: str) -> None:
    lines = {
        "search_endpoint_path": "    search_endpoint_path: /search\n",
        "filepath_json_key": "    filepath_json_key: path\n",
        "beets_field_names_to_query_param_names": "    beets_field_names_to_query_param_names: {album: name}\n",
    }
    section = "  downloader_hook:\n    base_url: http://dl.local\n" + "".join(
        line for name, line in lines.items() if name != omitted
    )
    with pytest.raises(BeetKeeperConfigError):
        load_config(_write_config(tmp_path, _BEETS_PREAMBLE + _BEETKEEPER_SECTION + section))
