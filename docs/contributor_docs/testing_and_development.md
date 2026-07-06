# Testing and Development

All commands in this doc are run from the repo root directory, unless explicitly noted otherwise.

## Pre-Reqs

1. Install `docker` (recommend either via [docker desktop](https://www.docker.com/products/docker-desktop/) or [colima](https://colima.run/)).
2. Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
3. Install pantsbuild either by running `./build_scripts/get-pants.sh` or through the other methods listed [here](https://www.pantsbuild.org/stable/docs/getting-started/installing-pants).
4. Install [`prek`](https://prek.j178.dev/installation/)
	1. run `prek install` from the repo root to set up the pre-commit  hooks.


## Local Testing

The beetkeeper repo uses [`pantsbuild`](https://www.pantsbuild.org/stable/docs/introduction/welcome-to-pants) (AKA "pants") extensively for testing and building both locally and in CI. As such we use the `pants` CLI for most, if not all of, the testing, linting, formatting, and artifact building.

Prior experience with pants is **_not required_**; however, you may find it helpful to bookmark the following pants doc pages for future reference:
1. [Targets and BUILD files](https://www.pantsbuild.org/stable/docs/using-pants/key-concepts/targets-and-build-files)
2. [Project Introspection](https://www.pantsbuild.org/stable/docs/using-pants/project-introspection)
3. [Command line help](https://www.pantsbuild.org/stable/docs/using-pants/command-line-help)


### Linting and Formatting


|  Action         |  Command            |  Description  |
| :-------------- | :-------------------|---------------|
| Lint Checks     | `pants lint ::`     | Runs all lint tools (`ruff`, `bandit`, `yamllint`, `taplo` (toml linter), `hadolint` (Dockerfile linter), `shellcheck`/`shfmt`, etc.) across the whole repo. |
| Type Checks     | `pants check ::`    | Runs `mypy` across the whole repo. |
| Formatting | `pants fmt fix ::`  | Runs all auto-formatting across the whole repo. |


### Testing

Tests run through Pants' built-in pytest: each `python_tests` file runs in its own sandbox, with
3rd-party dependencies supplied by the Pants resolve lockfiles under `3rdparty/` (regenerate with
`pants generate-lockfiles` after dependency changes). pytest itself and its plugins install from the
`[pytest].requirements` list in `pants.toml` — any plugin whose CLI options we pass (e.g. `pytest-socket`)
must be listed there. `pants test ::` also runs the repo-consistency check hooks (`hooks:uv-lockfile-check`,
`hooks:version-sync-check`).

To run all tests in the repo:

```shell
pants test ::
```

To run only the tests found under a specific path, run:

```shell
pants test < path-prefix-here >::
# Example: pants test src/python/tests/api_tests:: will only run tests found under src/python/tests/api_tests
```

To run pytest with pdb or other breakpoints enabled, run the command with the `--test-debug` flag. Example:

```shell
# If you set a breakpoint in a test within `src/python/tests/my_pytest_file.py`.
pants --test-debug test src/python/tests/my_pytest_file.py
```

For quick ad-hoc runs against the uv dev venv (no Pants sandboxing), `uv run --all-groups pytest ...`
also works.

### Running the Test Server

For manual, interactive testing of the web app, run:

```shell
./build_scripts/run-test-server.sh
```

This packages the server Docker image (`pants package //:beetkeeper-server-image`) and starts a container
from it, serving the app at <http://localhost:8337>. Press `Ctrl-C` to stop it. No configuration or host
data is required: the container entrypoint (`build_scripts/dev_scripts/test_container_init.sh`) generates a
throwaway beets/beetkeeper config under `/test_dirs` inside the container and runs the database migrations,
so everything is discarded when the container exits.

The script also mounts the repo's `src/python/beetkeeper/api/static` directory into the container and
symlinks it over the copy the PEX extracts at startup. This means edits to static files (CSS, HTML
templates, images, JS) on the host render on the next browser refresh — no image rebuild or container
restart needed. Changes to **Python** code, however, are baked into the PEX, so they require re-running the
script to rebuild the image.

### Building Artifacts Locally

The beetkeeper repo publishes the following artifacts for any given release:

|  Artifact Name         |  Type                       |  Description  |  Pants target  |
| :--------------------- | --------------------------- | :------------ | -------------: |
| `beetkeeper-server` | Docker image                | Self-hosted `beets` + `beetkeeper_plugin` wrapped by the `beetkeeper` server | `//:beetkeeper-server-image` |
| `beetkeeper.whl`       | Python library distribution | The beetkeeper server, published as a wheel file to PyPI | `src/python:beetkeeper-whl` |
| `beetkeeper-plugin` | Python library distribution | `beetsplug` plugin which pushes beets events to the beetkeeper server | `src/beetsplug:plugin-whl` |

To package all of the artifacts, run:

```shell
pants package ::
```

Or, to package only a specific artifact, run the command against the intended pants target.
For example, to only build the beetkeeper server wheel, you'd run:

```shell
pants package src/python:beetkeeper-whl
```

## CI and GitHub Actions

CI runs in GitHub Actions (`.github/workflows/`). The main workflow validates the repo through pants
(`pants update-build-files --check ::` then `pants lint check test ::`), builds the non-Docker artifacts
(`pants package --filter-target-type=-docker_image ::`) plus the Docker image in a separate job, and
verifies the docs build (`pants run docs:mkdocs-pex -- build --strict`). When modifying anything under
`.github/workflows`, we use two tools for local validation and testing:

1. [`actionlint`](https://github.com/rhysd/actionlint) — a static workflow linter
2. [`act`](https://github.com/nektos/act) — a tool for running GitHub actions workflows locally

NOTE: These are not substitutes for running the GitHub action changes in GitHub proper. They're intended for quicker detection of simple issues before pushing upstream.

### Using `actionlint`

`actionlint` checks the workflow YAML for syntax errors, invalid
`${{ }}` expressions, unknown action inputs, and shell problems in `run:` blocks (via `shellcheck`). It
runs automatically as a [prek](https://prek.j178.dev/) hook on commit and as the first step in CI — both
through the shared `hooks/actionlint.sh`, which uses a pinned `actionlint` (downloading it if it isn't on
your `PATH`). `yamllint` (part of `pants lint ::`) covers generic YAML issues like line length; `actionlint`
adds the GitHub-Actions-specific checks.

Run it on demand against every workflow:

```shell
hooks/actionlint.sh
```

### Using `act`

`act` executes the workflows in Docker containers which emulate the GitHub
runner. Install it with `brew install act`; repo-wide defaults live in `.actrc`. Use it in increasing order
of cost:

|  Command            |  Description  |
| :------------------ | :------------ |
| `act push --list`   | List the jobs the `push` event would trigger (instant, no Docker). |
| `act push --dryrun` | Print the execution plan without running steps (pulls the ~1 GB runner image on first use). |
| `act push`          | Run the full workflow locally. |

A full `act push` runs the **entire** workflow, including `pants package ::` building the Docker image
against your host Docker daemon — expect it to be slow and resource-heavy. `act` also cannot faithfully
reproduce runner-specific behavior (the GitHub Actions cache, `setup-python` fetching new versions), so a
real branch push remains the source of truth for those.
