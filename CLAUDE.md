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
- beets developer API: https://beets.readthedocs.io/en/v2.12.0/dev/

## Open `TODO[Claude]` items
- `src/python/beetkeeper/core/__init__.py:4` — for any beets public API/interface details, use the
  beets dev docs: https://beets.readthedocs.io/en/v2.12.0/dev/
- `src/python/beetkeeper/settings/user_config.py:22` — implement the `UserConfig` class definition
  (and subsequently the YAML schema).
