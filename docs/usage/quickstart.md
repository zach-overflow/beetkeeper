# Quick Start Demo

The fastest way to explore beetkeeper is to run it under Docker with a minimal demo config and click around
the web UI. This gets you a running instance in two commands — no existing beets library required (you can
point it at a real one later; see [Configuration](../configuration.md) and [Deployment](deployment.md)).

!!! info "Prerequisite"
    [Docker](https://docs.docker.com/get-docker/) installed and running.

## 1. Create a demo config

beetkeeper reads its settings from the optional `beetkeeper` section of a beets config. In an empty working
directory, save the following as `config.yaml` — a minimal demo config using in-container paths. It must be
named `config.yaml`, since `BEETSDIR` (below) points at the *directory* holding it:

```yaml title="config.yaml"
directory: /data/music
library: /data/library.db

beetkeeper:
  log_level: INFO
  server:
    hostname: 0.0.0.0   # bind all interfaces so the published port is reachable from the host
    port: 8337
    server_workers: 1   # single worker keeps the demo's SQLite simple
  database:
    sqlite_path: /data/beetkeeper.db   # on the persistent volume
```

## 2. Initialize the database (one-time)

beetkeeper does not auto-migrate. Create its tables once into a named volume (`beetkeeper-demo`):

```bash
docker run --rm \
  -e BEETSDIR=/config \
  -v "$(pwd)/config.yaml:/config/config.yaml:ro" \
  -v beetkeeper-demo:/data \
  ghcr.io/zach-overflow/beetkeeper:latest db upgrade
```

## 3. Run the server

```bash
docker run -d --name beetkeeper-demo \
  -e BEETSDIR=/config \
  -v "$(pwd)/config.yaml:/config/config.yaml:ro" \
  -v beetkeeper-demo:/data \
  -p 8337:8337 \
  ghcr.io/zach-overflow/beetkeeper:latest
```

## 4. Explore

Open **<http://localhost:8337/>** and try:

- **[The web interface](web-interface.md)** — run imports, browse the event history, and search your library.
- **[The REST API](rest-api.md)** — the same functionality for automation, with interactive docs at
  <http://localhost:8337/docs>.

## Tear down the demo

```bash
docker rm -f beetkeeper-demo
docker volume rm beetkeeper-demo    # discard the demo database
```

When you're ready to run beetkeeper for real, see [Deployment](deployment.md).
