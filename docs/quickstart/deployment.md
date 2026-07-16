# Deployment

This page covers running beetkeeper under Docker for real use. It mirrors the setup in the repo's
[`deploy/`](https://github.com/zach-overflow/beetkeeper/tree/main/deploy) directory, which includes an
example `config.yaml` (with container paths). beetkeeper reads its settings from that file's optional
top-level `beetkeeper` section; the rest is an ordinary beets config — see [Configuration](../configuration.md).

For a throwaway try-it-out run, start with the [Quick Start Demo](demo.md) instead.

## First-time setup

### 1. Get the image

Pull the published image (or build it locally with `pants package //:beetkeeper-server-image`):

```bash
docker pull ghcr.io/zach-overflow/beetkeeper:latest
```

### 2. Run the server

beetkeeper creates its database schema automatically at startup, into the persistent named volume
(`beetkeeper-data`) — no separate migration step is needed.

=== "docker compose"

    ```yaml title="compose.yaml"
    services:
      beetkeeper:
        image: ghcr.io/zach-overflow/beetkeeper:latest
        restart: unless-stopped
        stop_grace_period: 30s
        ports:
          - "8337:8337"
        environment:
          BEETSDIR: /config
        volumes:
          - /host/path/to/beetsdir:/beets:ro
          - /host/path/to/music/downloads:/downloads
          - /host/path/to/music/library:/music
          - beetkeeper-data:/data
    volumes:
      beetkeeper-data:
    ```

    ```bash
    docker compose up -d
    ```

=== "docker run"

    ```bash
    DEPLOY="$(pwd)/deploy"

    docker run -d --name beetkeeper \
		-e BEETSDIR=/config \
		-v /host/path/to/beetsdir:/beets:ro" \
		-v /host/path/to/music/downloads:/downloads \
		-v /host/path/to/music/library:/music \
		-p 8337:8337 \
		--stop-timeout 30 \
		ghcr.io/zach-overflow/beetkeeper:latest     # default CMD is `run`
    ```

### 3. Verify

```bash
docker logs -f beetkeeper                                        # watch startup
curl -s -o /dev/null -w '%{http_code}\n' localhost:8337/home     # 200
```

## Upgrading an existing install

When moving to a newer beetkeeper version, pull the new image and restart the server against the **same**
volume:

```bash
docker pull ghcr.io/zach-overflow/beetkeeper:latest
docker rm -f beetkeeper    # or: docker compose down
docker compose up -d       # or the `docker run` command from first-time setup step 2
```

Any schema migrations the new version brings are applied automatically at startup. Before migrating,
beetkeeper backs up the db file alongside itself (e.g. `beetkeeper.db.pre-<revision>.bak` on the
`beetkeeper-data` volume), so you can roll back if an upgrade doesn't go as planned. To manage migrations
manually instead, set `database.auto_upgrade: false` and use `beetkeeper db upgrade` — see
[Configuration](../configuration.md).

!!! warning "Never downgrade the app against a newer database"
    If the database was written by a newer beetkeeper version, the server refuses to start rather than
    downgrade the schema. Restore the matching `.bak` file (or upgrade beetkeeper) to recover.

## Teardown

```bash
docker rm -f beetkeeper
docker volume rm beetkeeper-data    # only if you want to discard the DB
```

## Notes

- **Config:** beetkeeper's settings live under the `beetkeeper` section of `config.yaml`; the same file is
  the beets config (`directory`, `library`, …). `BEETSDIR` points at the **directory** holding it (beets'
  own convention), and the file inside must be named `config.yaml`.
- **Volumes:** mount the config read-only (`:ro`); the DB lives on the read-write `beetkeeper-data` volume
  so it persists across restarts (and holds the automatic pre-migration `.bak` backups).
- **Workers / SQLite:** beetkeeper always runs a single server worker process — SQLite is effectively
  single-writer, so this is enforced rather than configurable (the old `server.server_workers` setting
  is ignored, with a warning, if still present).
- **Local disk only:** beetkeeper's database runs in SQLite's [WAL mode](https://sqlite.org/wal.html),
  which does not work over network filesystems — keep the data volume holding `database.sqlite_path` on
  local disk (expect `-wal`/`-shm` companion files next to the db file).
