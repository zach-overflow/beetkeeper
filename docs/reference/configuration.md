# Configuration schema

These models define every key beetkeeper accepts under the `beetkeeper` section of your beets config
(see [Configuration](../configuration.md) for a hand-written overview and example). They are generated
directly from the source, so they always match the version you are running.

::: beetkeeper.settings.user_config
    options:
      members:
        - UserConfig
        - ServerConfSection
        - DatabaseConfSection
        - load_config
        - BeetKeeperConfigError
