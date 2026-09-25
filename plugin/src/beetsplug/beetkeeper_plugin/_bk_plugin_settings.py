"""Wrapper models for the `beetkeeper_plugin` config section in beets' `config.yaml`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from confuse import ConfigError  # pants: no-infer-dep
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError  # pants: no-infer-dep

if TYPE_CHECKING:
    from confuse import Subview  # pants: no-infer-dep

_API_TOKEN_KEY: Final[str] = "api_token"
_DEFAULT_HOSTNAME: Final[str] = "127.0.0.1"
_DEFAULT_PORT: Final[int] = 8337


def _default_server_url_factory() -> HttpUrl:
    return HttpUrl(f"http://{_DEFAULT_HOSTNAME}:{_DEFAULT_PORT}")


class BkPluginConf(BaseModel):
    """
    Main pydantic wrapper model for the `beetkeeper_plugin` config section of beets' `config.yaml`.

    The `server_url` default must stay in agreement with the server's own `beetkeeper.server` defaults
    (`beetkeeper.settings.ServerConfSection`) WITHOUT either side reading the other's config section —
    the `test_configs_compat` integration test enforces this.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    server_url: HttpUrl = Field(default_factory=_default_server_url_factory)
    api_token: SecretStr | None = Field(default=None)


def load_config_section(plugin_confuse_view: Subview) -> BkPluginConf:
    """
    Loads the plugin's `BkPluginConf` pydantic model from its confuse config view (beets' config library).

    Blank string values are treated as unset (their defaults apply) and other string values are stripped.
    Raises `ValueError` on a config section that fails model validation, aborting plugin load: a malformed
    `server_url` would otherwise silently push events nowhere.
    """
    plugin_confuse_view[_API_TOKEN_KEY].redact = True
    try:
        raw_conf: dict[str, Any] = dict(plugin_confuse_view.flatten())
    except ConfigError:
        raw_conf = {}
    cleaned = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in raw_conf.items()
        if not (isinstance(value, str) and not value.strip())
    }
    try:
        return BkPluginConf.model_validate(cleaned)
    except ValidationError as e:
        raise ValueError(f"Invalid `beetkeeper_plugin` config section in the beets config:\n{e}") from e
