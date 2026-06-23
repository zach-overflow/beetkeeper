"""
Namespaced beets plugin package, which installs both beets and the beetkeeper standalone package.
https://beets.readthedocs.io/en/stable/dev/plugins/index.html#id5
"""

from beetsplug.beetkeeper_plugin.beetkeeper_plugin import BeetkeeperListener

__all__ = ["BeetkeeperListener"]
