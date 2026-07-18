"""beets plugin package for beetkeeper (imported by beets as `beetsplug.beetkeeper_plugin`).

beets' plugin loader imports `beetsplug.<name>` and instantiates the last `BeetsPlugin` subclass it finds
in that module's namespace, so the plugin class must be re-exported here at the package level.
"""

from beetsplug.beetkeeper_plugin.beetkeeper_plugin import BeetkeeperPlugin

__all__ = ["BeetkeeperPlugin"]
