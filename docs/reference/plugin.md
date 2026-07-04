# Plugin API

`beetkeeper-plugin` is the beets plugin that reports library events (imports, removals, file changes) from
your beets install to a running beetkeeper server, so the server's event history stays complete even for
imports run outside the UI. Install it alongside the server — see [Installation](../installation.md).

::: beetkeeper_plugin.beetkeeper_plugin
    options:
      members:
        - BeetkeeperPlugin
