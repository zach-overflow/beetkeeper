"""
Keeps the server's and the plugin's config models agreeing on the default server URL: by design neither
side reads the other's config section (`beetkeeper` vs `beetkeeper_plugin`), so nothing at runtime
guarantees the plugin's default push target matches where the server listens by default — this test does.
"""

from beetkeeper.settings import ServerConfSection
from beetsplug.beetkeeper_plugin._bk_plugin_settings import BkPluginConf


def test_default_server_urls_match() -> None:
    """The plugin's default `server_url` equals the URL built from the server's own bind defaults."""
    server_defaults = ServerConfSection()
    plugin_default_url = BkPluginConf().server_url.unicode_string().rstrip("/")
    assert plugin_default_url == f"http://{server_defaults.hostname}:{server_defaults.port}"
