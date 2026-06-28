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
| Lint Checks     | `pants lint ::`     | Runs all lint tools (`ruff`, `yamllint`, `taplo` (toml linter), `hadlo` (Dockerfile linter), etc.) across the whole repo. |
| Formatting | `pants fmt fix ::`  | Runs all auto-formatting across the whole repo. |


### Testing

To run all tests in the repo:

```shell
pants test ::
```

To run only the tests found under a specific path, run:

```shell
pants test < path-prefix-here >::
# Example: pants test src/beetsplug/tests:: will only run tests found under src/beetsplug/tests
```

To run pytest with pdb or other breakpoints enabled, run the command with the `--test-debug` flag. Example:

```shell
# If you set a breakpoint in a test withiin `src/python/tests/my_pytest_file.py`.
pants --test-debug test src/python/tests/my_pytest_file.py
```

### Building Artifacts Locally

The beetkeeper repo publishes the following artifacts for any given release:

|  Artifact Name         |  Type                       |  Description  |  Pants target  |
| :--------------------- | --------------------------- | :------------ | -------------: |
| `beetkeeper-server` | Docker image                | Self-hosted `beets` + `beetkeeper_plugin` wrapped by the `beetkeeper` server | `//:beetkeeper-server-image` |
| `beetkeeper.whl`       | Python library distribution | The beekteeper server, published as a wheel file to PyPI | `src/python:beetkeeper-whl` |
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
(`pants update-build-files --check ::` then `pants lint test ::`) and builds the release artifacts
(`pants package ::`). When modifying anything under `.github/worfklows`, we use two tools for local validation and testing:

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
