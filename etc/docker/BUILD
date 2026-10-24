shell_source(name="docker-entrypoint", source="docker-entrypoint.sh")

# Native single-arch image: `pants package` builds it for the host arch and loads it into the local daemon.
# CI builds this on a matrix of native runners (one arch each, no QEMU) and pushes per-arch tags that a merge
# job stitches into a multi-arch manifest list — see .github/workflows/release.yml. Both per-arch PEXes are
# dependencies so both enter the build context, which `context_root=""` roots at the repo root (so COPY paths
# are repo-relative); the Dockerfile's ARG TARGETARCH picks the matching one at COPY time.
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
        "//:license-file",
        ":docker-entrypoint",
        "//:beetkeeper-linux-amd64-pex",
        "//:beetkeeper-linux-arm64-pex",
    ],
)
