# https://www.pantsbuild.org/stable/docs/using-pants/validating-dependencies
__dependencies_rules__(("*", "*"))

file(name="pyproject", source="pyproject.toml")
file(name="uv-lockfile", source="uv.lock")
file(name="license-file", source="LICENSE.txt")
file(name="dockerfile", source="Dockerfile")
shell_source(name="docker-entrypoint", source="docker-entrypoint.sh")

# One thin single-platform PEX plus one scie ("standalone" binary) per complete platform, each pinned via
# `complete_platforms` so it carries only that platform's wheels and resolves them locally on any build host
# (macOS dev machine or native CI runner, no docker_environment / QEMU). Targets and outputs:
#   //:beetkeeper-<os>-<arch>-pex        -> dist/beetkeeper-<os>-<arch>-pex.pex
#   //:beetkeeper-<os>-<arch>-standalone -> dist/standalone/<os>-<arch>/beetkeeper-<scie platform> (+ .sha256)
# Only the linux `-pex` targets go into the image; its `ARG TARGETARCH` picks the matching file at COPY time.
app_server_pexes(
    complete_platforms=[
        "//3rdparty/platforms:linux-arm64",
        "//3rdparty/platforms:linux-amd64",
        "//3rdparty/platforms:macos-arm64",
        "//3rdparty/platforms:macos-amd64",
    ],
    dependencies=["//beetkeeper-core:app-requirements", "//beetkeeper-core:beetkeeper-whl", "//plugin:plugin-whl"],
)


# Native single-arch image: `pants package` builds it for the host arch and loads it into the local daemon.
# CI builds this on a matrix of native runners (one arch each, no QEMU) and pushes per-arch tags that a merge
# job stitches into a multi-arch manifest list — see .github/workflows/release.yml. Both per-arch PEXes are
# dependencies so both enter the build context (context_root=""); the Dockerfile's ARG TARGETARCH picks the
# matching one at COPY time.
docker_image(
    name="beetkeeper-server-image",
    source="Dockerfile",
    target_stage="app",
    context_root="",
    registries=["@ghcr"],
    repository="zach-overflow/beetkeeper",
    # RELEASE_TAG is the v-stripped version exported by the release workflow; local builds fall back to `dev`.
    image_tags=["latest", env("RELEASE_TAG", "dev")],
    dependencies=[
        ":license-file",
        ":docker-entrypoint",
        "//:beetkeeper-linux-amd64-pex",
        "//:beetkeeper-linux-arm64-pex",
    ],
)
