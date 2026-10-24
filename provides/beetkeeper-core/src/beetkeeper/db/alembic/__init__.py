"""
Alembic migration environment for beetkeeper's database.

    - `env.py`     — resolves the connection URL and runs migrations offline (`--sql`) or async-online.
    - `versions/`  — the migration scripts (initial schema + future revisions).

`target_metadata` is `SQLModel.metadata`. At runtime the `beetkeeper db ...` CLI builds the alembic
`Config` programmatically (see `beetkeeper.db.migrations`); the sibling `db/alembic.ini` is for manual
`alembic` CLI use / authoring new revisions with `--autogenerate`.
"""
