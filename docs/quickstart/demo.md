# Quick Start Demo

The fastest way to explore beetkeeper is to run it under Docker with a minimal demo config and click around
the web UI. This gets you a running instance in a single command — no existing beets library required (you can
point it at a real one later; see [Configuration](../configuration.md) and [Deployment](deployment.md)).

!!! info "Recommended"
    We recommend using [Docker](https://docs.docker.com/get-docker/) to run beetkeeper.
	
	However, for anyone wishing to run beetkeeper without Docker, you may use the standalone [PyPI package](https://pypi.org/project/beetkeeper/) instead.

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
  database:
    sqlite_path: /data/beetkeeper.db   # on the persistent volume
```

## 2. Run the server

beetkeeper creates its database (and applies any schema migrations) automatically at startup — no separate
initialization step.

=== "Docker"

	```bash
	docker run -d --name beetkeeper-demo \
		-e BEETSDIR=/config \
		-v "$(pwd):/config:ro" \
		-v beetkeeper-demo:/data \
		-p 8337:8337 \
		--stop-timeout 30 \
		ghcr.io/zach-overflow/beetkeeper:latest
	```

=== "Python Standalone"

    ```shell
	pip install beetkeeper
	export BEETSDIR=<path to folder holding beets config.yaml>
    beetkeeper run
    ```

## 3. Explore

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
