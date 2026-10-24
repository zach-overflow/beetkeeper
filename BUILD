# https://www.pantsbuild.org/stable/docs/using-pants/validating-dependencies
__dependencies_rules__(("*", "*"))

file(name="pyproject", source="pyproject.toml")
file(name="uv-lockfile", source="uv.lock")
file(name="license-file", source="LICENSE.txt")

# One thin single-platform PEX plus one scie ("standalone" binary) per complete platform, each pinned via
# `complete_platforms` so it carries only that platform's wheels and resolves them locally on any build host
# (macOS dev machine or native CI runner, no docker_environment / QEMU). Targets and outputs:
#   //:beetkeeper-<os>-<arch>-pex        -> dist/beetkeeper-<os>-<arch>-pex.pex
#   //:beetkeeper-<os>-<arch>-standalone -> dist/standalone/<os>-<arch>/beetkeeper-<scie platform> (+ .sha256)
# Only the linux `-pex` targets go into the image; its `ARG TARGETARCH` picks the matching file at COPY time.
app_server_pexes(
    complete_platforms=[
        "//etc/3rdparty/platforms:linux-arm64",
        "//etc/3rdparty/platforms:linux-amd64",
        "//etc/3rdparty/platforms:macos-arm64",
        "//etc/3rdparty/platforms:macos-amd64",
    ],
    dependencies=[
        "//provides/beetkeeper-core:app-requirements",
        "//provides/beetkeeper-core:beetkeeper-whl",
        "//provides/plugin:plugin-whl",
    ],
)
