# Release Management

How beetkeeper versions and publishes its release artifacts. All commands run from the repo root.

## What gets published

A release publishes three artifacts, all carrying the **same** semver:

| Artifact | Pants target | Destination |
| :------- | :----------- | :---------- |
| `beetkeeper` wheel | `src/python:beetkeeper-whl` | PyPI (`beetkeeper`) |
| `beetkeeper-plugin` wheel | `src/beetsplug:plugin-whl` | PyPI (`beetkeeper-plugin`) |
| `beetkeeper-server` image | `//:beetkeeper-server-image` | GHCR `ghcr.io/zach-overflow/beetkeeper` (`:latest` + `:<version>`) |

## Versioning model — single source of truth

The canonical version lives in one file: **`VERSION`** (repo root). It is *propagated* into the two
committed sites that the build backends actually read (setuptools builds each wheel from its own
`pyproject.toml`, so the value cannot be inherited from an ancestor file — it must be written into each):

| Site | Field | Drives |
| :--- | :---- | :----- |
| `src/python/beetkeeper/_version.py` | `__version__` | the `beetkeeper` wheel **and** the Docker image (its wheel is built from this source via `uv`) |
| `src/beetsplug/pyproject.toml` | `[project].version` | the `beetkeeper-plugin` wheel |

`hooks/version-sync.sh` is the propagator:

```shell
hooks/version-sync.sh           # write VERSION into both sites, then `uv lock`
hooks/version-sync.sh --check   # verify both sites equal VERSION (no writes); non-zero on drift
```

The version is **owned by committed source and validated in CI** — there is no in-CI stamping. A bump must
be committed (and tagged) by a human; the guards below ensure nothing drifts.

### Drift guards

| Guard | When | Catches |
| :---- | :--- | :------ |
| prek `version-sync` hook | local commit (`prek`) | `VERSION` / a version site committed out of sync |
| `version-sync-check` test_cmd | every `pants test ::` (branch + tag CI) | the same drift, repo-wide |
| `uv-lockfile-check` test_cmd | every `pants test ::` | forgot to `uv lock` after a plugin bump |
| `src/release_tests` (`-m release_tests`) | the release workflow, on a tag | committed version ≠ the pushed tag |

## Cutting a release (runbook)

1. **Bump + propagate** on a branch:
   ```shell
   echo "0.1.0" > VERSION          # the new semver, no leading `v`
   hooks/version-sync.sh           # propagates into both sites + re-locks
   ```
2. **Verify locally:**
   ```shell
   hooks/version-sync.sh --check   # ✅ version sync OK (0.1.0)
   pants lint test ::              # full validation (incl. version-sync-check + uv-lockfile-check)
   ```
3. **Commit and merge** `VERSION`, `_version.py`, `src/beetsplug/pyproject.toml`, and `uv.lock` to `main`.
4. **Tag and push** an exact `vMAJOR.MINOR.PATCH` tag on the merged commit:
   ```shell
   git tag v0.1.0 && git push origin v0.1.0
   ```
5. The **Release** workflow (`.github/workflows/release.yml`) runs automatically (see below). On success
   the image is on GHCR and both wheels are on PyPI at `0.1.0`.

> The git tag carries a leading `v` (GitHub release convention); every published *version id* (wheel
> versions + the `:<version>` image tag) is the `v`-stripped semver. The two must agree — that is exactly
> what `src/release_tests` asserts, failing the release early if a bump was forgotten.

## What the release workflow does

Triggered on `push` of any `v*` tag. The `release` job mirrors `build-and-test.yml` through
`pants lint test ::`, then:

1. **Version tag gate** — computes the `v`-stripped `version` and whether the tag is an exact
   `^v[0-9]+\.[0-9]+\.[0-9]+$` release tag (`is_release`, exposed as a job output).
2. **Validate release versions** — `uv run --all-groups pytest -m release_tests src/release_tests`
   (asserts committed versions agree with each other and, for a release tag, with the pushed tag).
3. **Build artifacts** — `pants package ::` (wheels → `dist/`, image → local daemon as
   `ghcr.io/zach-overflow/beetkeeper:latest`).
4. **Publish image + stage wheels** *(only when `is_release`)* — `pants publish //:beetkeeper-server-image`
   builds (cache hit) + pushes `ghcr.io/zach-overflow/beetkeeper` at `:latest` and `:<version>` (the `@ghcr`
   registry + `env("RELEASE_TAG", "dev")` image tag in `BUILD`); each wheel is uploaded as its own artifact
   for the next job.

A separate **`publish-pypi` job** (`needs: release`, `if: is_release`) then publishes the wheels to PyPI
via **OIDC trusted publishing**, bound to the **`pypi`** GitHub environment. It downloads the wheel
artifacts and runs `pypa/gh-action-pypi-publish` once per project (a minted OIDC token is project-scoped,
so each project is uploaded on its own). No PyPI API token is stored. Because the `pypi` environment
requires a reviewer, this job **pauses for manual approval** after the build + image push complete.

Every `v*` tag is built and validated; **only an exact `vMAJOR.MINOR.PATCH` tag is published.** A
pre-release tag (e.g. `v0.1.0-dev`) builds and validates but skips all publish steps — use it as a dry run.

## Required configuration

- **GHCR** — uses the workflow's built-in `GITHUB_TOKEN` (the `release` job grants `packages: write`); no
  extra secret.
- **PyPI** — uses **OIDC trusted publishing**; no stored token. Each PyPI project
  (`beetkeeper`, `beetkeeper-plugin`) must have a Trusted Publisher registered with: owner/repo
  `zach-overflow/beetkeeper`, workflow `release.yml`, and environment **`pypi`**. The `publish-pypi` job
  declares `environment: pypi` + `id-token: write` to mint the matching OIDC token.

## Troubleshooting

- **`version sync OK` fails / release test mismatch** — a version site is out of step with `VERSION`. Run
  `hooks/version-sync.sh`, commit, and re-tag.
- **`uv.lock is out of sync`** — re-run `hooks/version-sync.sh` (it runs `uv lock`) or `uv lock`, then
  commit `uv.lock`.
- **Release ran but nothing published** — the tag was not an exact `vMAJOR.MINOR.PATCH` (e.g. it had a
  `-dev` suffix); publish steps are gated off for non-release tags.
- **PyPI publish fails with a trusted-publisher / OIDC error** — the registered Trusted Publisher must
  match exactly: owner/repo `zach-overflow/beetkeeper`, workflow `release.yml`, environment `pypi`, on the
  correct project. A `pypi` environment protection rule (e.g. required reviewer) will also pause the job.
- **PyPI upload rejected as already existing** — the publish steps use `skip-existing`, so a re-run is
  safe; publishing a *new* release requires a *new* version (PyPI forbids overwriting an existing one).
