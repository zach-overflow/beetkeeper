# Using the CLI

beetkeeper ships a single `beetkeeper` command with a small set of subcommands. Every command reads your
beets config via `--config-path`/`-c` (or the `BEETKEEPER_CONFIG` environment variable) — see
[Configuration](../configuration.md).

## `beetkeeper run`

Runs the web server.

```shell
beetkeeper run --config-path /path/to/beets/config.yaml
```

Once running, open the web UI at `http://<hostname>:<port>/` (defaults to port `8337`).

## `beetkeeper db upgrade`

Applies database migrations up to a target revision (default: `head`). beetkeeper does **not** auto-migrate
on startup, so run this once before first use and again after upgrading to a version with new migrations.

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
