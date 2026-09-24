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
  database:
    # beetkeeper's own SQLite db (separate from the beets library db); created automatically on first run.
    sqlite_path: /beets/beetkeeper.db
  # Optional: require a login for all access (off by default).
  auth:
    enable_login_protection: true
    username: admin
    password: change-me
  # Optional: let beetkeeper ask your download client where a library entry came from (off by default).
  downloader_hook:
    base_url: http://qbittorrent:8080
    search_endpoint_path: /api/v2/torrents/info
    beets_field_names_to_query_param_names:
      album: name
    filepath_json_key: content_path
    replace_downloader_paths_prefix: /data/torrents/complete
```

## Settings

| Key                       | Type    | Default | Description                                                     |
| :------------------------ | :------ | :------ | :-------------------------------------------------------------- |
| `log_level`               | string  | —       | One of `CRITICAL`, `DEBUG`, `ERROR`, `INFO`, `NOTSET`, `WARNING`. |
| `server.hostname`         | string  | `127.0.0.1` | Interface to bind (e.g. `0.0.0.0` to listen on all interfaces; the default binds loopback only). |
| `server.port`             | int     | `8337`  | Port the server listens on (must be `> 0`).                     |
| `server.forwarded_allow_ips` | string | —    | Reverse-proxy addresses (comma-separated IPs and/or CIDR networks like `192.168.40.0/24`, or `"*"` for all) whose `X-Forwarded-*` headers the server trusts. The UI renders root-relative URLs and works through any proxy without this; set it behind a reverse proxy so the request scheme and client address reflect the real client (accurate logs, correct absolute URLs anywhere one is ever emitted). Hostnames are **not** supported — uvicorn compares the raw peer IP. Note that setting this **replaces** the loopback default, so include `127.0.0.1` if a local proxy is also in play. Unset, uvicorn's default applies (the `FORWARDED_ALLOW_IPS` env var, else loopback only). |
| `database.sqlite_path`    | path    | —       | Path to beetkeeper's own SQLite db (created automatically on first run). |
| `database.auto_upgrade`   | bool    | `true`  | Apply pending schema migrations automatically when the server starts (the db file is backed up first). When `false`, a stale schema fails startup until you run `beetkeeper db upgrade`. |
| `auth.enable_login_protection` | bool | `false` | Opt-in login protection: when `true`, every page and API route requires a logged-in session. |
| `auth.username`           | string  | —       | Login username. Required when `enable_login_protection` is `true`. |
| `auth.password`           | string  | —       | Login password. Required when `enable_login_protection` is `true`. |
| `auth.session_ttl_hours`  | int     | `168`   | How long a login session stays valid before a new login is required. |
| `downloads_path`          | path    | `/downloads` | The pre-import staging folder beetkeeper imports from (the container's `/downloads` mount). Downloader hook paths are mapped into it. |
| `downloader_hook.base_url` | URL    | —       | Base URL (with port) of your download client's REST API. Setting it enables the hook; the next three settings are then required. |
| `downloader_hook.search_endpoint_path` | string | — | Endpoint (relative to `base_url`) beetkeeper sends GET search requests to. |
| `downloader_hook.beets_field_names_to_query_param_names` | map | — | beets fields of the library entry being looked up → the query param name each is sent as (e.g. `album: name`). Empty fields are left out. |
| `downloader_hook.filepath_json_key` | string | — | JSON key in each search result holding the download's path (e.g. qBittorrent's `content_path`). beetkeeper uses the first result. |
| `downloader_hook.replace_downloader_paths_prefix` | string | `""` | Path prefix the download client reports which beetkeeper replaces with `downloads_path` — needed when the two run in containers with different mounts. Leave empty when both see the same paths. |
| `downloader_hook.api_key`  | string | —       | Bearer token sent in the `Authorization` header, if the client's API needs one. |

## Login protection

beetkeeper is single-user: enabling `auth.enable_login_protection` gates the whole app behind the one
configured `username`/`password` pair (there are no per-route permissions — a logged-in client can do
everything).

- **Browsers** are redirected to a `/login` page; a successful login stores the session in an
  `HttpOnly` cookie, and a **Log out** button appears in the navigation bar.
- **API clients** exchange the credentials for a bearer token via `POST /api/auth/login`, then send it as
  an `Authorization: Bearer <token>` header (revoke it with `POST /api/auth/logout`).
- The login endpoints, API docs, `/api/health`, and static assets stay reachable without a session.

Sessions are stored (hashed) in beetkeeper's database, so they survive restarts.

## Downloader hook

beetkeeper only knows where a library entry was imported *from* when the beetkeeper beets plugin reported
that import. Entries imported before beetkeeper was set up show **Not recorded** on the search page — and
without a source folder they cannot be imported afresh (say, to recover a track file beets dropped).

The optional `downloader_hook` section lets beetkeeper ask your download client instead. It is deliberately
generic — any client with a REST search endpoint can be wired up through config alone:

1. beetkeeper looks the entry up in the beets library and takes the fields named in
   `beets_field_names_to_query_param_names`, renaming each to its query param name.
2. It sends `GET <base_url><search_endpoint_path>?<params>` (with `Authorization: Bearer <api_key>` when
   set). The full request shape is documented as the `search-missing-source-path` webhook in the API docs.
3. The client answers with a JSON list of results (or a single object). beetkeeper reads
   `filepath_json_key` from the first one and maps the path onto `downloads_path` via
   `replace_downloader_paths_prefix`.

Run a lookup through `GET /api/import/reimport/find_missing_source_path`, or the **Find via downloader**
button on unrecorded search rows. A match is stored as the entry's **inferred** source path: the search page
shows it labelled *(inferred via downloader)* — for the album and each of its tracks — with an **Import from
here** link, and a later lookup replaces it. Inferred paths are kept in their own table, apart from source
paths *recorded* from the beetkeeper plugin's events; a recorded path always takes precedence.

!!! tip "Authoritative source"
    The table above is a friendly summary. For the exact field definitions, validation, and defaults, see the
    [`beetkeeper.settings.user_config`](https://github.com/zach-overflow/beetkeeper/blob/main/src/python/beetkeeper/settings/user_config.py)
    models in the source.

!!! warning "Separate database"
    `database.sqlite_path` is beetkeeper's own bookkeeping database — **not** your beets library database.
    It is created (and kept schema-current) automatically by `beetkeeper run`, or manually via
    `beetkeeper db upgrade` (see [the CLI](quickstart/cli.md)).

## The beets plugin (`beetkeeper_plugin`)

The [`beetkeeper-plugin`](https://pypi.org/project/beetkeeper-plugin/) package provides the beets-side
plugin that pushes library events (imports, removals) to the server's `/api/events` endpoints — this is
what populates the **Beets Events** page. Enable it like any beets plugin:

```yaml
plugins:
  - beetkeeper_plugin
```

Its own (optional) config section:

```yaml
beetkeeper_plugin:
  # Where to push events. Defaults to `http://127.0.0.1:8337` — matching the beetkeeper server's own
  # defaults, right for the usual same-container/same-host setup — so most installs need no section at all.
  server_url: http://127.0.0.1:8337
  # Only needed when the server runs with `auth.enable_login_protection`; leave unset otherwise.
  api_token: your-token-here
```

| Key          | Type   | Default                 | Description                                                     |
| :----------- | :----- | :---------------------- | :-------------------------------------------------------------- |
| `server_url` | url    | `http://127.0.0.1:8337` | Base URL of the beetkeeper server to push events to. Must be a valid `http(s)://` URL. |
| `api_token`  | string | —                       | Bearer token for the push requests, for servers running with login protection. When unset (or blank), pushes carry no auth at all. |

The section is validated when beets loads the plugin (see the
[`_bk_plugin_settings`](https://github.com/zach-overflow/beetkeeper/blob/main/src/beetsplug/beetkeeper_plugin/_bk_plugin_settings.py)
pydantic models): a malformed `server_url` fails plugin load with a clear validation error instead of
silently pushing events nowhere, and blank values are treated as unset (their defaults apply).

Push failures are logged and swallowed — an unreachable beetkeeper server never breaks the beets
operation that fired the event.
