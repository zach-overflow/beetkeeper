# Release Management

How beetkeeper versions and publishes its release artifacts. All commands run from the repo root.

## What gets published

A release publishes three artifacts, all carrying the **same** semver:

| Artifact | Pants target | Destination |
| :------- | :----------- | :---------- |
| `beetkeeper` wheel | `src/python:beetkeeper-whl` | PyPI (`beetkeeper`) |
| `beetkeeper-plugin` wheel | `src/beetsplug:plugin-whl` | PyPI (`beetkeeper-plugin`) |
| `beetkeeper-server` image | `//:beetkeeper-server-image` | GHCR `ghcr.io/zach-overflow/beetkeeper` (`:latest` + `:<version>`) |

The docs site (GitHub Pages) is also rebuilt and redeployed as part of every release: mike publishes
the release's `MAJOR.MINOR` docs version to the `gh-pages` branch and points the `latest` alias at it.

## Versioning model — the git tag is the source of truth

Both wheels are versioned from the `vMAJOR.MINOR.PATCH` git tag via Pants'
[`vcs_version`](https://www.pantsbuild.org/stable/reference/targets/vcs_version) target (setuptools-scm
under the hood); **no version string is committed anywhere**. The moving parts:

- Each distribution has a `vcs_version` target (`src/python/beetkeeper/BUILD`,
  `src/beetsplug/beetkeeper_plugin/BUILD`) that runs setuptools-scm against the real repo and generates a
  `_scm_version.py` module into every consuming Pants sandbox (dependency inference picks it up from the
  import in `_version.py`).
- Each package's committed `_version.py` re-exports the generated module, falling back to `0.0.0.dev0`
  where it doesn't exist — i.e. any build/run outside Pants, such as the uv dev venv.
- Each `pyproject.toml` resolves `dynamic = ["version"]` via
  `[tool.setuptools.dynamic] version = {attr = "<pkg>._version.__version__"}`, so the wheel metadata gets
  the generated version inside Pants and the dev placeholder under uv.
- On a checkout of the release tag (what the Publish workflow does), setuptools-scm yields the exact
  `MAJOR.MINOR.PATCH`; on any other commit it yields a dev version (`X.Y.Z.devN+g<hash>`), which is what
  local `pants package` produces.

> The git tag carries a leading `v` (GitHub release convention); every published *version id* (wheel
> versions + the `:<version>` image tag) is the `v`-stripped semver. They can no longer disagree — the
> version is derived from the tag.

## Cutting a release (runbook)

1. **Draft the release on GitHub**: use the "Draft a new release" button on the
   [releases page](https://github.com/zach-overflow/beetkeeper/releases). Set the **title to the bare
   semver** (`MAJOR.MINOR.PATCH`, no leading `v`), write the notes (see
   `.github/release_notes_template.md`), and click **Save draft** — do *not* publish, and the tag field is
   ignored (a draft creates no tag).
2. **Run the Release workflow**: Actions → *Release* → *Run workflow* (from `main`). It locates the draft,
   validates the repo, and builds every artifact without publishing anything.
3. **Approve the `release` environment prompt** once validation is green. The workflow then tags the
   validated commit `vX.Y.Z`, publishes the GitHub release, and hands off to the *Publish* workflow, which
   builds and publishes the wheels, the multi-arch image, and the docs site (PyPI and Pages keep their own
   environment approvals).

## What the Release workflow does (`.github/workflows/release.yml`)

Triggered manually via `workflow_dispatch` (must be run from the default branch):

1. **`prepare`** — finds the repo's single draft release, validates its title is `MAJOR.MINOR.PATCH`, and
   checks `v<title>` isn't already tagged.
2. **Validation, all in parallel and publishing nothing**:
   - `validate` — actionlint, `pants update-build-files --check ::`, `pants lint check test ::`, and a
     wheel build (versioned as a dev build — the tag doesn't exist yet).
   - `build-image` — the Docker image on native amd64 + arm64 runners (built, not pushed).
   - `docs-build` — `mkdocs build --strict`.
3. **`approve-and-tag`** — pauses on the **`release`** environment (the one manual gate). On approval, one
   API call flips the draft to published with `tag_name: vX.Y.Z`, which creates the tag on the validated
   commit.
4. **`publish`** — dispatches the Publish workflow (`gh workflow run publish.yml`) on the new tag's
   ref. Dispatch is the only viable hand-off: a tag created with the built-in `GITHUB_TOKEN` can never
   fire another workflow's `push` trigger (GitHub's recursive-workflow guard, from which
   `workflow_dispatch` is exempt), and a `workflow_call` hand-off breaks PyPI trusted publishing, which
   rejects reusable workflows.

## What the Publish workflow does (`.github/workflows/publish.yml`)

Dispatched by Release (or triggered by a manually pushed `vMAJOR.MINOR.PATCH` tag; it can also be run
by hand via Actions → Publish → Run workflow for an existing tag). Three build
jobs run in parallel from the tag's commit, then three publication jobs run in parallel once **all**
builds succeed:

| Build (parallel) | Publication (parallel, after all builds) | Approval gate |
| :--------------- | :--------------------------------------- | :------------ |
| `build-wheels` — both wheels, versioned from the tag checkout | `publish-pypi` — OIDC trusted publishing, one upload per project | `pypi` environment |
| `build-image` — native per-arch builds, exported as tarball artifacts | `publish-image` — push per-arch tags, stitch the `:<version>` + `:latest` manifest list with `buildx imagetools` | none (GHCR, `GITHUB_TOKEN`) |
| `build-docs` — `mkdocs build --strict` (validation only) | `docs-deploy` — mike deploys the `MAJOR.MINOR` docs version (+ `latest` alias) to `gh-pages` | `github-pages` environment |

## Required configuration

- **`release` environment** — must exist with a **required reviewer** (repo Settings → Environments);
  this is the single "proceed with the release?" prompt.
- **Tag ruleset** — no ruleset may have **Restrict creations** enabled for `v*` tags: `approve-and-tag`
  creates the release tag with the built-in `GITHUB_TOKEN`, which is rejected with "Cannot create ref due
  to creations being restricted" and *cannot* be added to a ruleset bypass list (only roles, teams, deploy
  keys, and installed GitHub Apps can). Restricting tag *updates/deletions* is fine. Note the trade-off:
  any write-access collaborator can then push a `v*` tag, which triggers the Publish workflow directly
  (PyPI/Pages publication stays environment-gated; the GHCR image push is not).
- **GHCR** — uses the built-in `GITHUB_TOKEN` (`packages: write`); no extra secret.
- **PyPI** — OIDC trusted publishing; no stored token. Each PyPI project (`beetkeeper`,
  `beetkeeper-plugin`) needs a Trusted Publisher registered for owner/repo `zach-overflow/beetkeeper`,
  workflow **`publish.yml`**, environment **`pypi`**. Publish always runs as its own top-level workflow
  (dispatched, never `workflow_call`ed) precisely because PyPI rejects reusable workflows.
- **GitHub Pages** — repo Pages source set to **"Deploy from a branch"** (`gh-pages`, root); mike creates
  the branch on the first release deploy. The `github-pages` environment holds any deploy approval rule
  (it gates the workflow's mike push, which is the publish event).

## Troubleshooting

- **`prepare` fails: "Expected exactly one draft release"** — either no draft exists yet (create one via
  the release form and *Save draft*), several drafts are lying around (delete the stale ones), or — if a
  draft definitely exists — the job's token can't see it: GitHub omits drafts from the list endpoint for
  tokens without push access, which is why the `prepare` job must keep `contents: write`.
- **`prepare` fails: title not `MAJOR.MINOR.PATCH`** — the draft's *title* is the version. Fix the title
  (bare semver, no `v`) and re-run the workflow.
- **`uv.lock is out of sync`** — run `uv lock` and commit the result.
- **Publish ran but wheels carry a dev version** — the build didn't see the release tag; the
  `build-wheels` job must check out `v<version>` with `fetch-depth: 0` (setuptools-scm needs the tag in
  the checkout).
- **PyPI publish fails with a trusted-publisher / OIDC error** — the registered Trusted Publisher must
  match exactly: owner/repo `zach-overflow/beetkeeper`, workflow `publish.yml`, environment `pypi`. Also
  note PyPI rejects reusable workflows outright, so Publish must never be converted to `workflow_call`.
- **PyPI upload rejected as already existing** — the publish steps use `skip-existing`, so a re-run is
  safe; publishing a *new* release requires a *new* version (PyPI forbids overwriting an existing one).
