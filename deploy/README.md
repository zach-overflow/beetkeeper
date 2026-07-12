# Running beetkeeper in Docker

Files here:

- `config.yaml` — the beets config (container paths). beetkeeper reads its settings from this file's
  optional top-level `beetkeeper` section; the rest is an ordinary beets config. `BEETSDIR` points at the
  directory holding it, so the file must be named `config.yaml`.

## 0. Build the image

```bash
pants package //:beetkeeper-server-image  # produces the image  ghcr.io/zach-overflow/beetkeeper:latest
```

## 1. Run the server

The app creates its database schema (and applies any pending migrations, after backing up the db file)
automatically at startup, into the persistent named volume (`beetkeeper-data`):

```bash
DEPLOY="$(pwd)/deploy"

docker run -d --name beetkeeper \
  -e BEETSDIR=/config \
  -v "$DEPLOY/config.yaml:/config/config.yaml:ro" \
  -v beetkeeper-data:/data \
  -p 8337:8337 \
  ghcr.io/zach-overflow/beetkeeper:latest          # default CMD is `run`
```

## 2. Verify

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

- **Config:** beetkeeper's settings live under the `beetkeeper` section of `config.yaml`; the same file is
  the beets config (`directory`, `library`, …). `BEETSDIR` points at the directory holding it.
- **Volumes:** the config file is mounted read-only (`:ro`); the DB (and, in this smoke-test config, the
  beets library/music) lives on the read-write `beetkeeper-data` volume so it persists across restarts
  (and holds the automatic pre-migration `.bak` backups).
- **Host paths:** the `$DEPLOY/...:/config/...` mounts assume you run these from the repo root. Adjust
  the left-hand (host) side to wherever your real config lives.
- **Workers/SQLite:** `server_workers` is 1 in the config — raising it risks SQLite "database is
  locked" errors under concurrent writes.
