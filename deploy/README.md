# Running beetkeeper in Docker

Files here:

- `beets-config.yaml` — the beets config (container paths). beetkeeper reads its settings from this file's
  optional top-level `beetkeeper` section; the rest is an ordinary beets config.

## 0. Build the image

```bash
pants package //:beetkeeper-server-image  # produces the image  ghcr.io/zach-overflow/beetkeeper:latest
```

## 1. Create the schema (one-time, and after any new migration)

The app does **not** auto-migrate on startup, so apply migrations once into a persistent named
volume (`beetkeeper-data`). The entrypoint is `beetkeeper`, so the trailing args run `beetkeeper db upgrade`:

```bash
DEPLOY="$(pwd)/deploy"

docker run --rm \
  -e BEETKEEPER_CONFIG=/config/beets-config.yaml \
  -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
  -v beetkeeper-data:/data \
  ghcr.io/zach-overflow/beetkeeper:latest db upgrade
```

## 2. Run the server

```bash
DEPLOY="$(pwd)/deploy"

docker run -d --name beetkeeper \
  -e BEETKEEPER_CONFIG=/config/beets-config.yaml \
  -v "$DEPLOY/beets-config.yaml:/config/beets-config.yaml:ro" \
  -v beetkeeper-data:/data \
  -p 8337:8337 \
  ghcr.io/zach-overflow/beetkeeper:latest          # default CMD is `run`
```

## 3. Verify

```bash
docker logs -f beetkeeper                       # watch startup
curl -s localhost:8337/home | head              # full page
curl -s localhost:8337/events | head            # full page
curl -s localhost:8337/fragment/nav-links       # HTMX fragment
curl -s -o /dev/null -w '%{http_code}\n' localhost:8337/static/css/classless.css   # 200
```

## Teardown

```bash
docker rm -f beetkeeper
docker volume rm beetkeeper-data    # only if you want to discard the DB
```

## Notes

- **Config:** beetkeeper's settings live under the `beetkeeper` section of `beets-config.yaml`; the same
  file is the beets config (`directory`, `library`, …). `BEETKEEPER_CONFIG` points at it.
- **Volumes:** the config file is mounted read-only (`:ro`); the DB (and, in this smoke-test config, the
  beets library/music) lives on the read-write `beetkeeper-data` volume so it persists across restarts.
  Both the migrate step and the server must use the same volume (they do above).
- **Host paths:** the `$DEPLOY/...:/config/...` mounts assume you run these from the repo root. Adjust
  the left-hand (host) side to wherever your real config lives.
- **Workers/SQLite:** `server_workers` is 1 in the config — raising it risks SQLite "database is
  locked" errors under concurrent writes.
