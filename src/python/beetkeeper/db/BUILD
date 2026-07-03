# Non-`.py` alembic config shipped inside the package (for manual `alembic` CLI use; the runtime
# `beetkeeper db ...` CLI builds its Config programmatically and does not require this file).
resource(name="alembic-ini", source="alembic.ini")
# `migrations.py` runs `alembic upgrade` against `./alembic` as `script_location`. Alembic loads the env
# and the `versions/` revision scripts DYNAMICALLY by path, so Pants' import inference can't see them —
# they must be explicit deps or they're absent from the sandbox and `upgrade head` becomes a no-op that
# creates no tables (tests then fail with "no such table"). Depending on them here (transitively via
# `migrations.py`) materializes the full migration env for every test that migrates a DB.
# The async DB stack pulls two runtime deps that are loaded dynamically (never imported by name), so Pants'
# import inference can't see either — declare them here so every DB-touching consumer (app + tests) gets
# them transitively, replacing the ad-hoc per-test-target declarations:
#   * `aiosqlite` — the async SQLite driver SQLAlchemy resolves from the `sqlite+aiosqlite://` URL.
#   * `greenlet`  — required internally by SQLAlchemy's async engine (`session.py`/`migrations.py`).
python_sources(
    dependencies=[
        ":alembic-ini",
        "./alembic:alembic",
        "./alembic/versions:versions",
        "//src/python:app-requirements#aiosqlite",
        "//src/python:app-requirements#greenlet",
    ]
)
