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

The tag itself is created by [cocogitto](https://docs.cocogitto.io/) (`cog bump --auto`) during the
Release workflow: the next semver is computed from the
[conventional commits](https://www.conventionalcommits.org/) landed on `main` since the previous release
tag (`fix:` → patch, `feat:` → minor, `BREAKING CHANGE` → major). Nobody picks a version number by hand.

## Conventional commits and `cog.toml`

PRs are **squash-merged**, so the **PR title becomes the commit that lands on `main`** (the branch's own
commits are discarded) and must be a conventional commit message — the Release workflow rejects the
release otherwise. In practice:

- Write PR titles as conventional commits: `feat(scope): ...`, `fix: ...`, `docs: ...`; mark breaking
  changes with `!` (e.g. `feat!: ...`). The *PR title* workflow (`.github/workflows/pr-title.yml`) runs
  `cog verify` on every PR and re-runs whenever the title is edited, so a non-compliant title can't be
  merged unnoticed.
- Keep each PR to **one logical change** — it gets exactly one changelog entry. If a PR contains two
  changelog-worthy changes, split it. Commits *within* a PR branch can be anything (`wip`, `fixup`);
  they're discarded by the squash.

Cocogitto's behavior is configured in `cog.toml` at the repo root:

- `tag_prefix = "v"` + `from_latest_tag = true` — cog reads/writes `vMAJOR.MINOR.PATCH` tags (matching
  the `vcs_version` scheme above) and only ever considers commits since the latest release tag, so
  history from before the cocogitto adoption is never checked.
- `branch_whitelist = ["main"]` — `cog bump` refuses to run anywhere but `main`.
- `disable_bump_commit = true` + `disable_changelog = true` — the bump is **tag-only**: no
  `chore(version)` commit and no committed `CHANGELOG.md`, so the release never pushes anything to
  `main` (branch protection and required status checks can't conflict with it) and the tag lands
  directly on the validated commit. The changelog lives on the
  [GitHub releases page](https://github.com/zach-overflow/beetkeeper/releases) instead.
- `post_bump_hooks` — `cog bump` itself is what pushes the new tag (the GitHub action wrapping it
  pushes nothing).
- `[changelog]` — the `remote` template renders GitHub-linked changelog entries;
  `cog changelog --at vX.Y.Z` generates each GitHub release's body straight from git history.

## Cutting a release (runbook)

1. **Land conventional commits on `main`.** The commits since the latest tag *are* the release: they
   determine the version bump and become the changelog. There is nothing to draft or write by hand.
2. **Run the Release workflow**: Actions → *Release* → *Run workflow* (from `main`). It checks the
   pending commits are conventional and warrant a bump, validates the repo, and builds every artifact
   without publishing anything.
3. **Approve the `release` environment prompt** once validation is green. `cog bump --auto` then tags
   the validated commit `vX.Y.Z` and pushes the tag (nothing else is pushed), the GitHub release is
   uploaded with the cog-generated changelog as its body, and the *Publish* workflow takes over to build
   and publish the wheels, the multi-arch image, and the docs site (PyPI and Pages keep their own
   environment approvals).

## What the Release workflow does (`.github/workflows/release.yml`)

Triggered manually via `workflow_dispatch` (must be run from the default branch):

1. **`check-commits`** — runs `cog check` (commits since the latest tag must be conventional) and
   `cog bump --auto --dry-run`, which fails the run early if nothing warrants a bump and surfaces the
   pending version as a notice.
2. **Validation, all in parallel and publishing nothing**:
   - `validate` — actionlint, `pants update-build-files --check ::`, `pants lint check test ::`, and a
     wheel build (versioned as a dev build — the tag doesn't exist yet).
   - `build-image` — the Docker image on native amd64 + arm64 runners (built, not pushed).
   - `docs-build` — `mkdocs build --strict`.
3. **`approve-and-tag`** — pauses on the **`release`** environment (the one manual gate). On approval,
   `cog bump --auto` (via `cocogitto/cocogitto-action`) computes the version and pushes the `vX.Y.Z` tag,
   which lands directly on the validated commit (the bump is tag-only — see the `cog.toml` notes above —
   so nothing is pushed to `main`); the job then generates the release changelog
   (`cog changelog --at vX.Y.Z`) and uploads the GitHub release with it as the body.
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
  pushes the release tag with the built-in `GITHUB_TOKEN`, which is rejected with "Cannot create ref due
  to creations being restricted" and *cannot* be added to a ruleset bypass list (only roles, teams, deploy
  keys, and installed GitHub Apps can). Restricting tag *updates/deletions* is fine. Note the trade-off:
  any write-access collaborator can then push a `v*` tag, which triggers the Publish workflow directly
  (PyPI/Pages publication stays environment-gated; the GHCR image push is not).
- **`main` branch protection** — optional and fully compatible: the release never pushes commits to
  `main` (the bump is tag-only), so any branch protection/ruleset can be enabled freely. In particular,
  making the *PR title* workflow's "Verify the PR title is a conventional commit" job a **required
  status check** is the recommended way to guarantee only conventional commits land on `main`.
- **Squash merge message defaults** — repo Settings → General → Pull Requests: keep only **squash
  merging** enabled, and set the default commit message to **"Pull request title"** (title = `PR_TITLE`,
  message = blank). This makes the verified PR title the squash commit verbatim and keeps inner-commit
  messages out of the body, where a stray `BREAKING CHANGE:` line would silently force a major bump.
- **GHCR** — uses the built-in `GITHUB_TOKEN` (`packages: write`); no extra secret.
- **PyPI** — OIDC trusted publishing; no stored token. Each PyPI project (`beetkeeper`,
  `beetkeeper-plugin`) needs a Trusted Publisher registered for owner/repo `zach-overflow/beetkeeper`,
  workflow **`publish.yml`**, environment **`pypi`**. Publish always runs as its own top-level workflow
  (dispatched, never `workflow_call`ed) precisely because PyPI rejects reusable workflows.
- **GitHub Pages** — repo Pages source set to **"Deploy from a branch"** (`gh-pages`, root); mike creates
  the branch on the first release deploy. The `github-pages` environment holds any deploy approval rule
  (it gates the workflow's mike push, which is the publish event).

## Troubleshooting

- **`check-commits` fails: `cog check` parse error** — a commit on `main` since the latest release tag
  isn't a valid conventional commit (usually a squash-merge PR title). History can't be rewritten on
  `main`, so land the remaining commits with compliant messages, or as a last resort adjust
  `[commit_types]` in `cog.toml`.
- **`check-commits` fails but the reported commit is the previous release's** — running the workflow with
  *zero* commits since the latest tag makes cog fall back to checking the tagged commit itself, which can
  produce a confusing parse error about the already-released commit. Either way the run is correctly
  telling you there is nothing to release.
- **`cog bump --auto --dry-run` fails: no bump warranted** — the commits since the latest tag are all
  non-bumping types (`chore:`, `docs:`, ...). Land at least one `fix:`/`feat:`/breaking change.
- **`approve-and-tag` fails pushing the release tag** — check the tag ruleset note under
  [Required configuration](#required-configuration).
- **`uv.lock is out of sync`** — run `uv lock` and commit the result.
- **Publish ran but wheels carry a dev version** — the build didn't see the release tag; the
  `build-wheels` job must check out `v<version>` with `fetch-depth: 0` (setuptools-scm needs the tag in
  the checkout).
- **PyPI publish fails with a trusted-publisher / OIDC error** — the registered Trusted Publisher must
  match exactly: owner/repo `zach-overflow/beetkeeper`, workflow `publish.yml`, environment `pypi`. Also
  note PyPI rejects reusable workflows outright, so Publish must never be converted to `workflow_call`.
- **PyPI upload rejected as already existing** — the publish steps use `skip-existing`, so a re-run is
  safe; publishing a *new* release requires a *new* version (PyPI forbids overwriting an existing one).
