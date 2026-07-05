__dependencies_rules__(("*", "*"))

file(name="pyproject", source="pyproject.toml")
file(name="uv-lockfile", source="uv.lock")
file(name="license-file", source="LICENSE.txt")
file(name="version-file", source="VERSION")
file(name="dockerfile", source="Dockerfile")

# Thin, single-linux-arch PEXes for the Docker image — one per arch, each pinned to that arch's
# `complete_platforms` so it carries only that arch's wheels. Unlike a
# no-`complete_platforms` PEX, these resolve the *linux* wheels regardless of the build host, so they build on
# a macOS dev machine as well as native CI runners (no docker_environment / QEMU needed). The image's
# `ARG TARGETARCH` selects the matching file at COPY time; both are dependencies of the image so both land in
# the build context. Output names use TARGETARCH's spelling (amd64/arm64), not the platform tag (aarch64).
pex_binary(
    name="beetkeeper-linux-amd64",
    script="beetkeeper",
    output_path="beetkeeper-linux-amd64.pex",
    include_requirements=True,
    include_sources=True,
    include_tools=True,
    inherit_path="fallback",
    complete_platforms=["//3rdparty/platforms:linux-amd64"],
    tags=["pex"],
    dependencies=["//src/python:app-requirements", "//src/python:beetkeeper-whl", "//src/beetsplug:plugin-whl"],
)
pex_binary(
    name="beetkeeper-linux-arm64",
    script="beetkeeper",
    output_path="beetkeeper-linux-arm64.pex",
    include_requirements=True,
    include_sources=True,
    include_tools=True,
    inherit_path="fallback",
    complete_platforms=["//3rdparty/platforms:linux-aarch64"],
    tags=["pex"],
    dependencies=["//src/python:app-requirements", "//src/python:beetkeeper-whl", "//src/beetsplug:plugin-whl"],
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
    dependencies=[":license-file", "//:beetkeeper-linux-amd64", "//:beetkeeper-linux-arm64"],
)
