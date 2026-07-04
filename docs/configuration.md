# Configuration

beetkeeper does **not** have its own config file. It reads its settings from an **optional** top-level
`beetkeeper:` section inside your existing **beets** config. A plain beets config without that section is
still a valid beets config — beetkeeper only requires the section when you run the server.

You tell beetkeeper which beets config to read via either:

- the `BEETKEEPER_CONFIG` environment variable, or
- the `--config-path` CLI flag (see [the CLI](usage/cli.md)).

## Example

```yaml
# ... your usual beets config (directory, library, plugins, ...) ...

beetkeeper:
  log_level: INFO
  server:
    hostname: 0.0.0.0
    port: 8080
    server_workers: 2
  database:
    # beetkeeper's own SQLite db (separate from the beets library db); created on first `beetkeeper db upgrade`.
    sqlite_path: /beets/beetkeeper.db
```

## Settings

| Key                       | Type    | Default | Description                                                     |
| :------------------------ | :------ | :------ | :-------------------------------------------------------------- |
| `log_level`               | string  | —       | One of `CRITICAL`, `DEBUG`, `ERROR`, `INFO`, `NOTSET`, `WARNING`. |
| `server.hostname`         | string  | —       | Interface to bind (e.g. `0.0.0.0` to listen on all interfaces). |
| `server.port`             | int     | `8080`  | Port the server listens on (must be `> 0`).                     |
| `server.server_workers`   | int     | `2`     | Number of server worker processes (must be `> 0`).             |
| `database.sqlite_path`    | path    | —       | Path to beetkeeper's own SQLite db (created on first migration). |

!!! tip "Authoritative source"
    The table above is a friendly summary. For the exact field definitions, validation, and defaults, see the
    [`beetkeeper.settings.user_config`](https://github.com/zach-overflow/beetkeeper/blob/main/src/python/beetkeeper/settings/user_config.py)
    models in the source.

!!! warning "Separate database"
    `database.sqlite_path` is beetkeeper's own bookkeeping database — **not** your beets library database.
    It is created when you first run `beetkeeper db upgrade` (see [the CLI](usage/cli.md)).
