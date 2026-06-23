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
pants package //:beetkeeper-app-image     # build app docker image
pants package //:beetkeeper-test-image    # build test docker image (FROM the app image)
pants package ::                      # Packages all pants targets which support the package command.
uv lock                               # regenerate lockfile after dep changes
uv lock --check                       # verify lockfile is current (also gated in Dockerfile)
```
Lint/type/security logic is shared with prek + CI via `hooks/*.sh` (ruff, mypy, bandit,
uv-lockfile-check). Install git hooks with `prek install`.

## Docker
- Single `Dockerfile`, two stages → two `docker_image` targets in root `BUILD`.
- `beetkeeper-test-image` does `FROM beetkeeper-app-image:app` (Pants substitutes the built tag);
  it depends on `:beetkeeper-app-image` so the app layers are reused and the test build context
  doesn't re-`COPY` app sources. If you uncomment a `COPY` in a stage, add the matching source
  dependency to that `docker_image` target.

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

- **beets integration model (blocking).** Subprocess `beet` CLI vs. beets Python API is undecided and
  `beets` is not a declared dependency. See `core/beet_commands.py`, `core/__init__.py`.
- **persistence layer.** No engine/session/`get_session`, no DB URL in `UserConfig`, `Job` lacks
  `table=True`, alembic is an empty placeholder. See `db/__init__.py`, `db/models.py`,
  `db/alembic/__init__.py`, `settings/user_config.py`.
- **request/response schema location** is unset. See `core/beet_commands.py`.
- **UI wiring + bugs.** `ui_router` is never mounted; `ui_routes/__init__.py` has a broken import
  (`python.beetkeeper...`); `example_ui_router` has a wrong template `name` prefix, a misleading `/config`
  prefix, and a missing return type hint; `search_page.py` is an empty leftover. See `api/ui_routes/*`,
  `api/fastapi_app.py`.
- **router prefix collision.** `files_router` and `import_router` both use `prefix="/import"`. See
  `api/api_routes/files_router.py`. Placeholder `foo`/`/login/access-token` endpoints remain across routers.
- **templating engine.** `jinja2-fragments` is a dep but `constants.TEMPLATES` is plain `Jinja2Templates`;
  full-page vs. HTMX-fragment rendering is undecided. See `api/constants.py`.
- **auth scope** is unspecified (placeholder `/login/access-token`). See `api/api_routes/config_router.py`.
- **`beetkeeper run` / uvicorn.** `reload=True` + `workers>1` conflict, nonexistent/CWD-relative
  `reload_dirs`, wrong `--config-path` help, `None` config-path crash. See `main.py`.
- **`UserConfig`** still needs its real schema. See `settings/user_config.py`.
- **test scaffolding.** `src/python/tests` (BUILD, `conftest.py`, an `anyio_backend` fixture, a TestClient
  fixture) does not exist yet, though CLAUDE.md's test rules assume it. `@pytest.mark.anyio` needs a
  backend chosen (asyncio vs. trio).


## Coding style and conventions

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
