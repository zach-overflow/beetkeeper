# CLAUDE.md

Dev notes for `beetkeeper` — a self-hosted FastAPI web app for managing [beets](https://beets.io/).
Source root is `src/python` (package: `src/python/beetkeeper`).

## Build tooling
- **Pants 2.32** is the build system (`pants.toml`). Run `pants <goal> ::` for everything.
- **uv** is the resolver (`[python] resolver = "uv"`, `enable_resolves = false`). The repo is a
  uv **workspace**: root `pyproject.toml` is the workspace root; `src/python/pyproject.toml` is the
  member that holds the real distribution `[project]`. Keep `uv.lock` in sync (`uv lock`).

## Two pyproject.toml files (intentional — don't merge)
- **Root `pyproject.toml`**: tool config only (ruff, mypy, pytest, bandit), `[dependency-groups]`
  dev deps, and `[tool.uv.workspace]`. No `[project]` table here.
- **`src/python/pyproject.toml`**: the distribution's `[project]` (name, deps, scripts, metadata)
  + `[build-system]`. It lives in the source root so setuptools' PEP 517 backend (run there by
  Pants) reads it. Version is dynamic: `[tool.setuptools.dynamic] version = {attr =
  "beetkeeper._version.__version__"}`, sourced from `src/python/beetkeeper/_version.py`.
- The wheel is built with `generate_setup=False` (see `src/python/BUILD`), so Pants does NOT inject
  metadata — runtime deps/scripts are maintained by hand in `src/python/pyproject.toml` and must
  stay consistent with what the code imports.

## Testing — IMPORTANT
- We do **not** use Pants' built-in pytest (its 3rd-party-plugin support needs a separate resolve).
  `python_tests` targets set `skip_tests=True` (in `src/python/tests/BUILD`), so the `test` goal
  ignores them. `[pytest].skip` is a no-op for the test goal and is deliberately NOT set.
- Real testing runs through the `//:pytest` `test_shell_command` (`uv run --all-groups pytest`),
  defined via the `test_cmd` macro in `build_scripts/pants_macros.py`.
- `pants test ::` runs `//:pytest`, plus `hooks:mypy` and `hooks:bandit` (also `test_shell_command`s).

## Common commands
```bash
pants test ::                         # uv-pytest (//:pytest) + mypy + bandit
pants lint ::                         # ruff, shellcheck, shfmt, hadolint, taplo, visibility
pants check ::                        # (mypy is run via hooks:mypy in the test goal, not check)
pants package src/python:beetkeeper-whl   # build the wheel -> dist/
pants package //:beetkeeper-server-image  # build app docker image
pants package ::                      # Packages all pants targets which support the package command.
uv lock                               # regenerate lockfile after dep changes
uv lock --check                       # verify lockfile is current (gated in prek + CI)
```
Lint/type/security logic is shared with prek + CI via `hooks/*.sh` (ruff, mypy, bandit,
uv-lockfile-check). Install git hooks with `prek install`.

## Docker
- The `Dockerfile` has an `ffmpeg` fetch stage + the final `app` stage; only `app` is packaged, as the
  single `//:beetkeeper-server-image` `docker_image` target in root `BUILD`. The image is named/pushed via
  the `@ghcr` registry (`ghcr.io/zach-overflow/beetkeeper`); see `pants.toml` `[docker.registries.ghcr]` and
  the `env("RELEASE_TAG", "dev")` tag in `BUILD`.
- The `app` stage runs no `uv`/resolve — it just COPYs a thin, single-arch PEX (`//:beetkeeper-linux-<arch>`, one per
  linux arch via `complete_platforms`, selected by `ARG TARGETARCH`). `pants package` builds only the host
  arch; CI builds + pushes the image per-arch on native runners (no QEMU) and stitches a multi-arch manifest
  list — see `.github/workflows/release.yml`.

## Relevant public docs
- Pants: https://www.pantsbuild.org/stable/docs/introduction/welcome-to-pants
- `python_distribution` target: https://www.pantsbuild.org/stable/reference/targets/python_distribution
- Pants pytest subsystem (why we avoid it): https://www.pantsbuild.org/stable/reference/subsystems/pytest#requirements
- uv workspaces: https://docs.astral.sh/uv/concepts/projects/workspaces/
- beets developer docs index page: https://beets.readthedocs.io/en/v2.12.0/dev/
	- beets API reference: https://beets.readthedocs.io/en/v2.12.0/api/index.html
	- Overview of beets' **internal** API for its core database features.
- FastAPI docs
- <!-- TODO[Claude]: this docs bullet was left blank — fill in (or remove) the intended reference. -->

## Open `TODO[Claude]` items
Inline `TODO[Claude]:` comments now mark each open question in the relevant file. Highest-impact first:

- **beets integration model — DECIDED + scaffolded.** Drive beets **in-process via its Python API** (not
  the `beet` CLI); beetkeeper and beets are co-located. `core/` is the only package that imports beets:
  `library.py` (async one-shot ops, write-serialized via a shared `CapacityLimiter(1)`), `import_jobs.py`
  (job state + decision DTOs), `import_worker.py` (dedicated single-consumer worker; an `ImportSession`
  subclass whose interactive hooks bridge from beets' pipeline threads to the event loop via an anyio
  `BlockingPortal`; cooperative abort). **Wired into the app:** lifespan background worker, JSON
  `api/api_routes/import_router.py`, HTMX `api/ui_routes/import_ui_fragments_router.py` + `/import` page,
  injected via `api/dependencies.py`. **Multi-worker + persistent:** job state lives in the DB
  (`core/import_store.py`, tables `import_job`/`import_lock`); imports are serialized node-wide by a leased
  lock (leader election) and decisions are delivered through the DB, so it's correct across
  `server_workers > 1` and survives restarts (orphan recovery on takeover). beets internals are
  version-pinned; mypy `beets.*` override in root pyproject.
- **persistence layer — DONE.** Async SQLAlchemy/SQLModel engine + `get_session`/`SessionDep`
  (`db/session.py`), a `database` section in `UserConfig`, and a programmatic alembic setup
  (`db/migrations.py`, `db/alembic/`) with an initial migration. DB is constructible via `beetkeeper db
  upgrade` (online) or `--sql` (offline). The three `/api/events` endpoints now persist `ListenerEvent` +
  `AlbumEvent`/`TrackEvent` rows via `SessionDep`. Verified by `tests/db_tests/` + `tests/api_tests/`.
- **request/response schema location — DONE.** Event API models live in `api/api_models/` (now with a
  `BUILD` file, so Pants infers it and it ships in the wheel).
- **templating engine.** `jinja2-fragments` is a dep but `constants.TEMPLATES` is plain `Jinja2Templates`;
  full-page vs. HTMX-fragment rendering is undecided. See `api/constants.py`.
- **auth scope** is unspecified — beetkeeper has no auth/users yet. Decide whether it's in scope
  (single-user self-hosted vs. multi-user) and document the choice.
- **`beetkeeper run` / uvicorn.** `reload=True` + `workers>1` conflict, nonexistent/CWD-relative
  `reload_dirs`, wrong `--config-path` help, `None` config-path crash. See `main.py`.
- **`UserConfig`** still needs its real schema. See `settings/user_config.py`.
- **test scaffolding — partially done.** `src/python/tests/conftest.py` now provides the `anyio_backend`
  fixture (asyncio); `tests/db_tests/` has real fixtures + tests. A shared FastAPI `TestClient`/async-client
  fixture for route tests is still TODO.


## Coding style and conventions

### In-code comments
In-code comments (`#`, `/* */`, etc., across Python, BUILD, config, CI, and CSS) are **discouraged**. Write
self-explanatory code and let names, types, and docstrings carry the intent. Only add a comment when it
explains something genuinely **unexpected or unintuitive** — a workaround, a subtle gotcha, or a non-obvious
constraint a competent reader couldn't infer from the code. Such cases should be rare. When one is warranted,
keep it **brief** (ideally one line) and, where useful, link out (GitHub issue thread, doc, etc.) rather than
explaining at length. (Python docstrings are documentation, not comments, and are encouraged.)

### Python source code
1. Write code with the expectation that it may be running within an asynchronous event loop.
	- Use the [anyio](https://anyio.readthedocs.io/en/stable/) library instead of the builtin `asyncio` library.
	- Prefer async coroutine definitions for FastAPI route definitions.
2. Whenever possible, aim to keep the code modular. Avoid monolithic files in preference of breaking out into functional domains.
	- The source code under `src/python/beetkeeper` shows a starting point for this structure, but feel free to create or consolidate things if needed.
3. Type hints are required.
4. Test code should live under `src/python/tests`, and not colocated with the source code, as some Pantsbuild examples show.

#### Frontend

1. The frontend should be handled ONLY by the following, both for any static components, as well as for dynamic HTML + event-based DOM manipulation:
	1. A monolithic classless CSS file at `src/python/beetkeeper/api/static/css/classless.css`
	2. [HTMX](https://htmx.org/docs/) (vendored in-repo, and baked into the common base HTML template at `src/python/beetkeeper/api/static/html_templates/base_template.html`.)
	3. Any pure, simple javascript -- only if absolutely needed -- and should be defined in the common shared base HTML template within a `<script> block.
2. Read the docstring at `src/python/beetkeeper/api/ui_routes/__init__.py` for details on the frontend code structure expectations. 
	
3. Do not use ANY javascript framework or any other additional frontend library other than <!-- TODO[Claude]: this rule is truncated — state the allowed exception (HTMX only?) so it is enforceable. Also note the preceding two list items were both numbered "2". -->

### Test code

1. Use `pytest`. Do not use the `unittest` builtin library.
2. Use of `pytest.mark.parametrize` and `pytest.fixture` are the preferred ways to generate test cases and reduce test code repetition.
3. Type hints are required in test code too.
	* This is true even when using pytest's "built in" fixtures, such as [`tmp_path`](https://docs.pytest.org/en/stable/how-to/tmp_path.html#the-tmp-path-fixture), or `mocker` from `pytest-mock`.

#### Mocks

1. Use any mock tooling from `pytest-mock`. Avoid using features from `unittest.mock` unless necessary.
2. Do not use mock decorators (e.g. `@patch(...)`).
3. Use `@pytest.mark.anyio` for async tests. Do not use `pytest-asyncio`.
4. Tests should never make real network calls.
	* When testing any FastAPI route functions, use testing tools FastAPI offers. (see [here](https://fastapi.tiangolo.com/tutorial/testing/), and the relevant testing pages under the [advanced user guide](https://fastapi.tiangolo.com/advanced/async-tests/).)
