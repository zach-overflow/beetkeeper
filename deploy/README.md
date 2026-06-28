# Running beetkeeper in Docker

Files here:

- `beetkeeper.docker.yaml` — the server config (container paths; see mounts below).
- `beets-config.yaml` — placeholder beets config (only needs to exist for now).

> **Prerequisite:** the app image must build first. As of now `pants package ::` fails at the
> in-image `uv lock --check` gate due to a uv/lockfile version skew — see the
> `TODO: upgrade uv to 0.11.x` in the repo `Dockerfile`. Once uv is on 0.11.x and `uv.lock` is
> regenerated, the steps below work as written.

## 0. Build the image

```bash
pants package //:beetkeeper-app-image     # produces the image  beetkeeper-app-image:app
```

## 1. Create the schema (one-time, and after any new migration)

The app does **not** auto-migrate on startup, so apply migrations once into a persistent named
volume (`beetkeeper-data`). The entrypoint is `beetkeeper`, so the trailing args run `beetkeeper db upgrade`:

```bash
DEPLOY="$(pwd)/deploy"

docker run --rm \
  -e BEETKEEPER_CONFIG=/config/beetkeeper.docker.yaml \
  -v "$DEPLOY/beetkeeper.docker.yaml:/config/beetkeeper.docker.yaml:ro" \
  -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
  -v beetkeeper-data:/data \
  beetkeeper-app-image:app db upgrade
```

## 2. Run the server

```bash
DEPLOY="$(pwd)/deploy"

docker run -d --name beetkeeper \
  -e BEETKEEPER_CONFIG=/config/beetkeeper.docker.yaml \
  -v "$DEPLOY/beetkeeper.docker.yaml:/config/beetkeeper.docker.yaml:ro" \
  -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
  -v beetkeeper-data:/data \
  -p 8080:8080 \
  beetkeeper-app-image:app          # default CMD is `run`
```

## 3. Verify

```bash
docker logs -f beetkeeper                       # watch startup
curl -s localhost:8080/home | head              # full page
curl -s localhost:8080/events | head            # full page
curl -s localhost:8080/fragment/nav-links       # HTMX fragment
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/static/css/classless.css   # 200
```

## Teardown

```bash
docker rm -f beetkeeper
docker volume rm beetkeeper-data    # only if you want to discard the DB
```

## Notes

- **Volumes:** config files are mounted read-only (`:ro`); the DB lives on the read-write
  `beetkeeper-data` volume so it persists across restarts. Both the migrate step and the server must
  use the same volume (they do above).
- **Host paths:** the `$DEPLOY/...:/config/...` mounts assume you run these from the repo root. Adjust
  the left-hand (host) side to wherever your real config lives.
- **Workers/SQLite:** `server_workers` is 1 in the config — raising it risks SQLite "database is
  locked" errors under concurrent writes.
- **Beets config:** `beets-config.yaml` only needs to exist today. Point `beets_config_filepath` at your
  real beets config (and mount it) once beets integration is implemented.
