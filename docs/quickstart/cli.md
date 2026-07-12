# Using the CLI

beetkeeper ships a single `beetkeeper` command with a small set of subcommands. Every command reads your
beets config via `--config-path`/`-c` (the config file), or the `BEETSDIR` environment variable (the
directory holding your beets `config.yaml`) — see [Configuration](../configuration.md).

## `beetkeeper run`

Runs the web server.

```shell
beetkeeper run --config-path /path/to/beets/config.yaml
```

Once running, open the web UI at `http://<hostname>:<port>/` (defaults to port `8337`).

Before serving, `run` automatically creates the beetkeeper database (first run) or applies any pending
schema migrations (after a version upgrade), backing up the db file alongside itself first. Set
`database.auto_upgrade: false` to require manual migrations instead — see
[Configuration](../configuration.md).

## `beetkeeper db upgrade`

Applies database migrations up to a target revision (default: `head`). With the default
`database.auto_upgrade: true` you normally never need this — `beetkeeper run` migrates on startup. Use it
when `auto_upgrade` is disabled, or with `--sql` to review the DDL offline.

```shell
beetkeeper db upgrade --config-path /path/to/beets/config.yaml
```

- `--revision <id>` — target a specific revision instead of `head`.
- `--sql` — offline mode: print the DDL to stdout instead of applying it.

## `beetkeeper db downgrade`

Reverts migrations down to a target revision (for example `base` to drop all beetkeeper tables).

```shell
beetkeeper db downgrade --revision base --config-path /path/to/beets/config.yaml
```

!!! tip
    Run `beetkeeper --help` (or `beetkeeper db --help`) to see all options for your installed version.
