# Using the REST API

Everything you can do in beetkeeper's [web interface](web-interface.md) you can also do over its REST API.
This is what makes beetkeeper suitable for automation — dropping it into a larger, hands-off music pipeline
rather than driving everything by hand.

At a high level, the API lets you:

- **Run and track imports** — kick off an import of a directory, then poll its status and answer any
  decisions beets needs (for example, which candidate release to apply) — the same flow the UI drives.
- **Clean-slate an entry** — `POST /api/import/clean_slate` removes a library album (or standalone track)
  like `beet remove -d`, then imports its raw source folder afresh as an ordinary, tracked import job.
  `GET /api/import/clean_slate/preview` dry-runs it first: what would be deleted, what the source holds,
  blocking errors and warnings, and whether the fewer-files opt-in (`allow_fewer_files`) is needed.
- **Recover an unrecorded source folder** — `POST /api/import/find_missing_source_path` asks your
  configured [download client](../configuration.md#downloader-hook) where a library entry was downloaded
  to, for entries imported before beetkeeper was tracking them.
- **Read the event history** — query the record of album/track imports, file changes, and removals, so an
  external system can react to what beetkeeper (and beets) has done.
- **Search the library** — run [beets queries](https://beets.readthedocs.io/en/stable/reference/query.html)
  against your collection and get structured results back.
- **Check health** — a lightweight endpoint for readiness/liveness probes.

Responses are JSON, and the API follows standard HTTP conventions (status codes, verbs). It's an ordinary
FastAPI application, so a running instance also serves **interactive Swagger UI at `/docs`** and the raw
schema at `/openapi.json` — point them at your own server (e.g. <http://localhost:8337/docs>) to try
requests live. Swagger UI is the complete, always-current endpoint-by-endpoint reference (paths,
parameters, and request/response schemas).
