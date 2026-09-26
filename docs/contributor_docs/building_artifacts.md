# Building Artifacts

How beetkeeper's build artifacts are produced with Pants. All commands run from the repo root.

| Artifact | Pants target | Notes |
| :------- | :----------- | :---- |
| `beetkeeper` wheel | `beetkeeper-core:beetkeeper-whl` | pure-python, `py3-none-any` |
| `beetkeeper-plugin` wheel | `plugin:plugin-whl` | pure-python |
| application PEXes | `//:beetkeeper-<slug>-pex` | thin, single-platform; the linux ones are bundled into the image |
| standalone binaries | `//:beetkeeper-<slug>-standalone` | scie: the PEX plus a lazily fetched, stripped CPython; lands at `dist/standalone/<slug>/beetkeeper-<scie platform>` (+ `.sha256`; the intermediate PEX beside it is `beetkeeper`) |
| server image | `//:beetkeeper-server-image` | GHCR (`db upgrade` / `run`) |

`<slug>` is one of `linux-amd64`, `linux-arm64`, `macos-amd64`, `macos-arm64`.

```bash
pants package //:beetkeeper-server-image   # builds the host-arch image (+ its PEX)
pants package //:beetkeeper-macos-arm64-standalone
pants package beetkeeper-core:beetkeeper-whl
```

## The application PEXes and standalone binaries (`//:beetkeeper-<slug>-{pex,standalone}`)

Both flavours are emitted per platform by the `app_server_pexes` macro (`build_scripts/pants_macros.py`, called
from the root `BUILD`). Each is a `pex_binary` pinned via [`complete_platforms`][cp] to one platform, so it
carries only that platform's native wheels (e.g. `pydantic_core`). `complete_platforms` lets PEX resolve those
foreign wheels **locally**, on a macOS dev machine or a native CI runner, without a foreign interpreter or
emulator, so the same `pants package` works everywhere. The `-pex` targets are plain PEX files; the
`-standalone` targets wrap the same PEX in a [scie](https://science.scie.app) that fetches a stripped
python-build-standalone CPython on first run, so the binary also runs on machines with no Python installed.

The Docker image bundles only the two linux `-pex` files; the `Dockerfile`'s `ARG TARGETARCH` selects the
matching one at COPY time. The macOS platforms exist for the standalone binaries.

A **complete platform** is a JSON description of a target interpreter: its PEP 508 marker environment plus the
full list of wheel tags it accepts. They live at `3rdparty/platforms/<slug>.json` and are exposed as `file`
targets by `3rdparty/platforms/BUILD`.

[cp]: https://www.pantsbuild.org/stable/docs/python/overview/pex#generating-the-complete_platforms-file

### Regenerating the complete-platform JSONs

The JSONs are produced only by `build_scripts/generate-complete-platforms.sh`. Do **not** hand-edit or
hand-copy subsets: a truncated tag list silently drops generic tags like `py3-none-any` and breaks pure-python
wheel resolution.

Regenerate when:

- the target Python minor changes (`FROM python:X.Y-...` in the `Dockerfile`, `interpreter_constraints` in
  `pants.toml`);
- the Docker base image changes (its glibc sets the `manylinux_2_NN` ceiling of the linux tags);
- Pants' pinned `[pex-cli]` version changes (pex computes the tag list);
- a platform slug is added.

Dependency or lockfile changes do **not** require regeneration.

```bash
./build_scripts/generate-complete-platforms.sh                     # all four slugs
./build_scripts/generate-complete-platforms.sh macos-arm64 macos-amd64
```

Per slug the script runs `pex3 interpreter inspect --markers --tags --indent=2` on the target interpreter,
drops the machine-specific `path` key, prepends a `__meta_data__` line recording the interpreter, its source and
the pex version, validates the result (expected `sys_platform` / `platform_machine` / `python_version`,
non-empty tags that include `py3-none-any`) and only then replaces `3rdparty/platforms/<slug>.json`.

| Slug | Interpreter | Needs |
| :--- | :---------- | :---- |
| `linux-amd64`, `linux-arm64` | the `Dockerfile` `app` stage base image, via `docker run --platform linux/<arch>` | `docker` (the non-native arch runs under Docker's emulation) |
| `macos-arm64` | uv-managed `cpython-<X.Y>-macos-aarch64-none` (python-build-standalone, the family the scie fetches) | an Apple-silicon Mac with `uv` |
| `macos-amd64` | uv-managed `cpython-<X.Y>-macos-x86_64-none` | a Mac with `uv`; on Apple silicon also Rosetta 2 (`softwareupdate --install-rosetta`) |

`jq` and `pants` must be on `PATH`. The inputs are derived from the repo and can be overridden:

| Variable | Default | Purpose |
| :------- | :------ | :------ |
| `PEX_VERSION` | Pants' pinned `[pex-cli]` version | pex release that runs the inspection |
| `DOCKER_IMAGE` | the `Dockerfile` `app` stage base image | interpreter for the linux slugs |
| `PYTHON_VERSION` | `MAJOR.MINOR` of `DOCKER_IMAGE`'s tag | selects uv's CPython for the macOS slugs |

Caveats:

- The macOS tag list tops out at the macOS version of the generating host (`macosx_15_0_*` on a 15.x host), so
  a PEX built from it could select a wheel newer than an older macOS can load. The wheels in the lockfile are
  tagged `macosx_10_x` / `macosx_11_0`, so this does not bite in practice.
- The linux tag list tops out at the base image's glibc (`manylinux_2_36` for bookworm).
- uv's python-build-standalone and the Docker image may sit at different `3.X` patch levels; only
  `python_full_version` differs and nothing in the lockfile depends on it.
- `platform_release`, `platform_version` and `__meta_data__` change on every run (kernel strings, macOS
  version); a regeneration diff that touches only those is a no-op.

Verify a regeneration by building a target and checking the bundled native wheel:

```bash
jq -r '.__meta_data__, (.compatible_tags | length), .compatible_tags[0]' 3rdparty/platforms/*.json
pants package //:beetkeeper-macos-amd64-pex
unzip -l dist/beetkeeper-macos-amd64-pex.pex | grep -o 'pydantic_core-[^/]*\.whl' | sort -u
```

### FAQ

**The JSON files list `py38-*` and `cp310-*` tags — does the PEX run on Python 3.8 / 3.10?**
No. `compatible_tags` lists the wheels a **cp314** interpreter is willing to install, ordered by
preference — not interpreters that can run the PEX. The list runs downward for backward compatibility:
`py38-none-*` / `py3-none-any` are pure-Python wheels (a "3.8+, no C" wheel also runs on 3.14), and
`cp310-abi3-*` are stable-ABI wheels (abi3 is forward-compatible, so a 3.10-ABI extension loads on 3.14).
Note the files contain only `cp310-abi3`, never `cp310-cp310` — a genuine 3.10-only binary wheel is *not*
accepted. The actual runtime floor is 3.14, pinned by the JSON's `marker_environment.python_full_version`
and the target's `interpreter_constraints = [">=3.14,<3.15"]` (`pants.toml`); the PEX rejects a 3.8/3.10
interpreter at launch. The older tags simply let the 3.14 build reuse older pure-python/abi3 wheels when no
cp314-specific wheel exists — which is exactly why the full tag list matters (drop `py3-none-any` and
pure-python deps like `aiosqlite` stop resolving).

**Why not one fat multi-platform PEX for all arches?**
A single PEX bundling every platform's wheels would carry four copies of each native wheel (`pydantic_core`,
`numpy`, ...) of which a given host can use only one. Since each image is one arch and each standalone binary
one platform, a per-platform PEX is strictly smaller. The `complete_platforms` mechanism could produce a fat PEX
(list all platforms on one `pex_binary`), but nothing consumes one today.

**With `execution_mode="venv"`, does the PEX pick up libraries from the virtualenv it's invoked from?**
No. venv mode is an internal startup optimization: on first run PEX materializes its **own** bundled
distributions into a private venv under `PEX_ROOT` and re-execs into it for faster imports. It does not see
the ambient environment's `site-packages`. PEXes are hermetic by default. Ambient-library visibility is a
separate knob — [`inherit_path`][ip] (`PEX_INHERIT_PATH`): `false` (default, isolated), `fallback` (PEX wins,
ambient fills gaps), or `prefer` (ambient wins). The image PEXes set `inherit_path="fallback"` so a derived
image can `pip install` an extra beets plugin and have the PEX pick it up.

[ip]: https://www.pantsbuild.org/stable/reference/targets/pex_binary#inherit_path


### Generating OpenAPI Spec JSON

To regenerate the OpenAPI spec JSON for the user reference site, run the following command:

```bash
pants run build_scripts:openapi-json-exporter
```
