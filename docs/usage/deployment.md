# Deployment

This page covers running beetkeeper under Docker for real use. It mirrors the setup in the repo's
[`deploy/`](https://github.com/zach-overflow/beetkeeper/tree/main/deploy) directory, which includes an
example `beets-config.yaml` (with container paths). beetkeeper reads its settings from that file's optional
top-level `beetkeeper` section; the rest is an ordinary beets config — see [Configuration](../configuration.md).

For a throwaway try-it-out run, start with the [Quick Start Demo](quickstart.md) instead.

## First-time setup

### 1. Get the image

Pull the published image (or build it locally with `pants package //:beetkeeper-server-image`):

```bash
docker pull ghcr.io/zach-overflow/beetkeeper:latest
```

### 2. Create the schema (one-time)

beetkeeper does **not** auto-migrate on startup. Apply migrations once into a persistent named volume
(`beetkeeper-data`). The image entrypoint is `beetkeeper`, so the trailing args run `db upgrade`:

```bash
DEPLOY="$(pwd)/deploy"

docker run --rm \
  -e BEETKEEPER_CONFIG=/config/beets-config.yaml \
  -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
  -v beetkeeper-data:/data \
  ghcr.io/zach-overflow/beetkeeper:latest db upgrade
```

### 3. Run the server

=== "docker compose"

    ```yaml title="compose.yaml"
    services:
      beetkeeper:
        image: ghcr.io/zach-overflow/beetkeeper:latest
        restart: unless-stopped
        ports:
          - "8080:8080"
        environment:
          BEETKEEPER_CONFIG: /config/beets-config.yaml
        volumes:
          - ./deploy/beets-config.yaml:/config/beets-config.yaml:ro
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
      -e BEETKEEPER_CONFIG=/config/beets-config.yaml \
      -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
      -v beetkeeper-data:/data \
      -p 8080:8080 \
      ghcr.io/zach-overflow/beetkeeper:latest          # default CMD is `run`
    ```

### 4. Verify

```bash
docker logs -f beetkeeper                                        # watch startup
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/home     # 200
```

## Upgrading an existing install

When moving to a newer beetkeeper version:

### 1. Pull the new image

```bash
docker pull ghcr.io/zach-overflow/beetkeeper:latest
```

### 2. Apply any new migrations

New versions may add migrations. Stop the server, then run `db upgrade` against the **same** volume before
starting the new version (the app does not migrate itself):

```bash
docker rm -f beetkeeper    # or: docker compose down

DEPLOY="$(pwd)/deploy"
docker run --rm \
  -e BEETKEEPER_CONFIG=/config/beets-config.yaml \
  -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
  -v beetkeeper-data:/data \
  ghcr.io/zach-overflow/beetkeeper:latest db upgrade
```

### 3. Restart the server

Start the server again with the new image (`docker compose up -d`, or the `docker run` command from
first-time setup step 3). Your data persists because it lives on the `beetkeeper-data` volume.

!!! tip "Back up first"
    Before upgrading, back up the `beetkeeper-data` volume (it holds beetkeeper's SQLite database) so you
    can roll back if a migration doesn't go as planned.

## Teardown

```bash
docker rm -f beetkeeper
docker volume rm beetkeeper-data    # only if you want to discard the DB
```

## Notes

- **Config:** beetkeeper's settings live under the `beetkeeper` section of `beets-config.yaml`; the same
  file is the beets config (`directory`, `library`, …). `BEETKEEPER_CONFIG` points at it.
- **Volumes:** mount the config read-only (`:ro`); the DB lives on the read-write `beetkeeper-data` volume
  so it persists across restarts. The migrate step and the server **must** use the same volume.
- **Workers / SQLite:** keep `server.server_workers` low — raising it risks SQLite "database is locked"
  errors under concurrent writes.
