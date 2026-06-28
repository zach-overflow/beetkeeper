# `beetkeeper.db`

beetkeeper's own database layer (a SQLite DB, **separate** from the beets library db). Its schema is
owned entirely by **alembic migrations** — `SQLModel.metadata.create_all` is never used at runtime, so
migrations are the single source of truth.

## Layout

| Path | Purpose |
| --- | --- |
| `models.py` | SQLModel ORM tables (`ListenerEvent`, `AlbumEvent`, `TrackEvent`). |
| `session.py` | Async engine + `async_sessionmaker`, the `get_session` dependency, and `SessionDep`. |
| `migrations.py` | Builds the alembic `Config` programmatically and wraps `upgrade`/`downgrade`. |
| `alembic.ini` | Config for the **manual** `alembic` CLI (authoring/inspecting). Not used at runtime. |
| `alembic/env.py` | The migration environment: `target_metadata = SQLModel.metadata`, async-online + offline. |
| `alembic/versions/` | The migration scripts. |

The connection URL comes from `UserConfig.database` (see `beetkeeper.settings`).

## Applying migrations

Runtime / operators use the CLI (it builds the alembic `Config` from your YAML config, no `alembic.ini`
needed):

```bash
beetkeeper db upgrade   -c /path/to/config.yaml              # apply everything (to "head")
beetkeeper db upgrade   -c /path/to/config.yaml --sql        # offline: print the DDL instead of applying
beetkeeper db downgrade -c /path/to/config.yaml --revision base
```

## Adding a new revision when the models change

1. **Edit the models** in `models.py` (add/modify a `SQLModel` table or column).

2. **Autogenerate a revision.** Point alembic at a throwaway SQLite DB via `-x db_url=...` and let it
   diff the models against an empty database:

   ```bash
   alembic -c src/python/beetkeeper/db/alembic.ini \
       -x db_url=sqlite+aiosqlite:///"$(mktemp -u).db" \
       revision --autogenerate -m "describe your change"
   ```

   Alternatively, set `BEETKEEPER_CONFIG=/path/to/config.yaml` (env.py will read the DB URL from it) and
   drop the `-x db_url=...` argument. The new script lands in `alembic/versions/`.

3. **Review the generated script.** Autogenerate is a starting point, not gospel:
   - SQLite cannot `ALTER` columns in place, so env.py enables **batch mode** (`render_as_batch=True`);
     column changes render as `with op.batch_alter_table(...)` blocks. Check those are correct.
   - SQLModel's `AutoString` is rendered as `sa.String()` by a `render_item` hook in `env.py`, so
     generated scripts need **no `import sqlmodel`**.
   - Autogenerate does **not** reliably detect: table/column renames (it sees a drop + add — fix by hand),
     `CHECK` constraints, or some server-default changes.

4. **Verify it applies and round-trips:**

   ```bash
   alembic -c src/python/beetkeeper/db/alembic.ini \
       -x db_url=sqlite+aiosqlite:///"$(mktemp -u).db" upgrade head
   ```

5. **Run the sync tests** (these fail if the models and migrations have drifted):

   ```bash
   uv run --all-groups pytest ./src/python/tests/db_tests
   # or the full gate: pants test ::
   ```

   See `src/python/tests/db_tests/test_alembic_and_models_synced.py` — `test_no_pending_autogenerate_diff`
   is the canonical check that "models == migrated schema".

6. **Commit** both the model change and the new `alembic/versions/*.py` script together.

### Editing vs. adding migrations

Once a migration has been released/applied anywhere, **do not edit it** — add a new revision instead.
(The single pre-release initial migration in this repo was an exception, regenerated while the schema was
still unpublished.)

### Notes

- `alembic/versions/__init__.py` exists so Pants treats the directory as a package; alembic ignores it
  when scanning for revisions.
- Foreign keys: SQLite only enforces them when `PRAGMA foreign_keys=ON`, which `session.make_engine`
  sets per connection — so the `ON DELETE CASCADE`s work at runtime and in the model tests.
- New non-`.py` files added under `alembic/` must be registered as Pants `resource`s and listed in
  `[tool.setuptools.package-data]` (see how `alembic.ini` / `script.py.mako` are wired) to ship in the wheel.
