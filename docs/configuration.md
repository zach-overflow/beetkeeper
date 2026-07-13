# Configuration

beetkeeper does **not** have its own config file. It reads its settings from an **optional** top-level
`beetkeeper:` section inside your existing **beets** config. A plain beets config without that section is
still a valid beets config — beetkeeper only requires the section when you run the server.

You tell beetkeeper which beets config to read via either:

- the `BEETSDIR` environment variable — the **directory** holding your beets `config.yaml` (beets' own
  convention), or
- the `--config-path` CLI flag — the path to the config file itself (see [the CLI](quickstart/cli.md)).

## Example

```yaml
# ... your usual beets config (directory, library, plugins, ...) ...

beetkeeper:
  log_level: INFO
  server:
    hostname: 0.0.0.0
    port: 8337
    server_workers: 2
  database:
    # beetkeeper's own SQLite db (separate from the beets library db); created automatically on first run.
    sqlite_path: /beets/beetkeeper.db
  # Optional: require a login for all access (off by default).
  auth:
    enable_login_protection: true
    username: admin
    password: change-me
```

## Settings

| Key                       | Type    | Default | Description                                                     |
| :------------------------ | :------ | :------ | :-------------------------------------------------------------- |
| `log_level`               | string  | —       | One of `CRITICAL`, `DEBUG`, `ERROR`, `INFO`, `NOTSET`, `WARNING`. |
| `server.hostname`         | string  | —       | Interface to bind (e.g. `0.0.0.0` to listen on all interfaces). |
| `server.port`             | int     | `8337`  | Port the server listens on (must be `> 0`).                     |
| `server.server_workers`   | int     | `2`     | Number of server worker processes (must be `> 0`).             |
| `database.sqlite_path`    | path    | —       | Path to beetkeeper's own SQLite db (created automatically on first run). |
| `database.auto_upgrade`   | bool    | `true`  | Apply pending schema migrations automatically when the server starts (the db file is backed up first). When `false`, a stale schema fails startup until you run `beetkeeper db upgrade`. |
| `auth.enable_login_protection` | bool | `false` | Opt-in login protection: when `true`, every page and API route requires a logged-in session. |
| `auth.username`           | string  | —       | Login username. Required when `enable_login_protection` is `true`. |
| `auth.password`           | string  | —       | Login password. Required when `enable_login_protection` is `true`. |
| `auth.session_ttl_hours`  | int     | `168`   | How long a login session stays valid before a new login is required. |

## Login protection

beetkeeper is single-user: enabling `auth.enable_login_protection` gates the whole app behind the one
configured `username`/`password` pair (there are no per-route permissions — a logged-in client can do
everything).

- **Browsers** are redirected to a `/login` page; a successful login stores the session in an
  `HttpOnly` cookie, and a **Log out** button appears in the navigation bar.
- **API clients** exchange the credentials for a bearer token via `POST /api/auth/login`, then send it as
  an `Authorization: Bearer <token>` header (revoke it with `POST /api/auth/logout`).
- The login endpoints, API docs, `/api/health`, and static assets stay reachable without a session.

Sessions are stored (hashed) in beetkeeper's database, so they survive restarts and work across all
`server_workers`.

!!! tip "Authoritative source"
    The table above is a friendly summary. For the exact field definitions, validation, and defaults, see the
    [`beetkeeper.settings.user_config`](https://github.com/zach-overflow/beetkeeper/blob/main/src/python/beetkeeper/settings/user_config.py)
    models in the source.

!!! warning "Separate database"
    `database.sqlite_path` is beetkeeper's own bookkeeping database — **not** your beets library database.
    It is created (and kept schema-current) automatically by `beetkeeper run`, or manually via
    `beetkeeper db upgrade` (see [the CLI](quickstart/cli.md)).
