"""
Placeholder submodule for maintaining any alembic migration information within the app itself.
See example below:
    https://github.com/fastapi/full-stack-fastapi-template/tree/master/backend/app/alembic

TODO[Claude]: This is an empty placeholder. To make migrations work, decide on and add:
    - `alembic.ini` (or programmatic Config) and an `env.py` that targets `SQLModel.metadata`
      (importing `beetkeeper.db.models` so all tables are registered as target_metadata).
    - The DB URL wiring: env.py must read the same connection URL as `beetkeeper.db` (see its TODO).
    - How migrations are invoked (manual `alembic` CLI vs. run-on-startup) and where `versions/` scripts go.
    - Pants/uv: confirm these non-`.py` config files are captured by the right BUILD targets.
"""
