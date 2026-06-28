FROM python:3.14-slim-bookworm AS ffmpeg

# --- Stage 1: fetch a pinned, checksum-verified static ffmpeg ---
# Replaces Debian's `ffmpeg` package, whose hard deps (libavdevice/libavfilter -> SDL, mesa-GL, libllvm15,
# flite TTS) added ~390 MB of video/GL code that beets' audio analysis (replaygain) never uses. These are
# BtbN/FFmpeg-Builds "gpl" static builds (latest stable release, n8.1.2), pinned to an IMMUTABLE dated
# release tag + per-arch SHA256, so the download is reproducible and tamper-evident. Only the `ffmpeg`
# binary is kept — beets' replaygain backend needs just ffmpeg (the build also ships ffprobe/ffplay, ~137 MB
# each; if you use the `convert` plugin, also install /tmp/ff/bin/ffprobe below).
# To bump: pick a newer immutable `autobuild-*` tag + stable `n*` version from
# https://github.com/BtbN/FFmpeg-Builds/releases , then update the tag/version/build + BOTH SHA256s
# (`sha256sum ffmpeg-<version>-<linux64|linuxarm64>-<build>.tar.xz`).
ENV FFMPEG_TAG=autobuild-2026-06-27-13-21 \
	FFMPEG_VERSION=n8.1.2 \
	FFMPEG_BUILD=gpl-8.1 \
	FFMPEG_SHA256_AMD64=1fa7d66a8bc3cd5f7b340e365d274106f182ea14269851230c83e4f69a57fc65 \
	FFMPEG_SHA256_ARM64=9c31feb2fb0bb87eafb9432f58e7ef06ca47269f281aefbdaeadfdf57b5c585e
# Transient fetch-only tools in a throwaway stage; pinning their versions would break on every Debian point
# release for no benefit (this stage's output is just the verified binary), so DL3008 is ignored here.
# hadolint ignore=DL3008
RUN apt-get update \
	&& apt-get install \
	-y --no-install-recommends \
	ca-certificates curl xz-utils \
	&& apt-get clean \
	&& rm -rf /var/lib/apt/lists/*
ARG TARGETARCH
RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) btbn_arch="linux64";    sha="${FFMPEG_SHA256_AMD64}" ;; \
        arm64) btbn_arch="linuxarm64"; sha="${FFMPEG_SHA256_ARM64}" ;; \
        *) echo "unsupported TARGETARCH='${TARGETARCH:-unset}' (need a BuildKit builder)" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_TAG}/ffmpeg-${FFMPEG_VERSION}-${btbn_arch}-${FFMPEG_BUILD}.tar.xz"; \
    curl -fsSL "${url}" -o /tmp/ffmpeg.tar.xz; \
    echo "${sha}  /tmp/ffmpeg.tar.xz" > /tmp/ffmpeg.sha256; \
    sha256sum -c /tmp/ffmpeg.sha256; \
    mkdir -p /tmp/ff; \
    tar -xJf /tmp/ffmpeg.tar.xz -C /tmp/ff --strip-components=1; \
    install -m 0755 /tmp/ff/bin/ffmpeg /usr/local/bin/ffmpeg; \
    /usr/local/bin/ffmpeg -version

# --- Stage 2: the application image ---
FROM python:3.14-slim-bookworm AS app

# ghcr.io supported labels found at link below:
# https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
LABEL org.opencontainers.image.source="https://github.com/zach-overflow/beetkeeper" \
	org.opencontainers.image.description="A highly configurable, self-hosted app for beets music library management. Supports both automated and manual workflows." \
	org.opencontainers.image.licenses="AGPL-3.0-or-later"

# UV_SYSTEM_PYTHON: Force uv to use the container's pre-installed system Python instead of downloading its own
# UV_PROJECT_ENVIRONMENT: Ensure uv installs in container do not create a virtualenv (since it is not needed in a container)
ENV UV_SYSTEM_PYTHON=1 UV_PROJECT_ENVIRONMENT=/usr/local/
# https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
# Pinned (not `:latest`) to match the uv that writes uv.lock — a different uv version can record a
# different set of platform wheels and fail the in-image `uv lock --check`. Keep this in sync with the
# local/CI uv version (currently 0.11.23) whenever uv.lock is regenerated.
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /uvx /bin/
# Pinned static ffmpeg from the `ffmpeg` stage above (used by beets' replaygain backend). No apt is needed
# in this image: `git` isn't used (no VCS deps), and ffmpeg is a self-contained static binary.
COPY --from=ffmpeg /usr/local/bin/ffmpeg /usr/local/bin/
WORKDIR /app

COPY LICENSE.txt pyproject.toml uv.lock ./
# BOTH uv workspace members' `[project]` must be present for `uv lock --check` (it validates the whole
# workspace). The app image only installs the `beetkeeper` server package (`--package beetkeeper`), so the
# client plugin's *source* is not needed here — only its pyproject, for the lock check.
COPY src/python/pyproject.toml src/python/pyproject.toml
COPY src/beetsplug/pyproject.toml src/beetsplug/pyproject.toml
COPY src/python/beetkeeper/ /app/src/python/beetkeeper
# `--no-dev`: uv installs the `dev` group by default even with `--package`; without this the app image
# ships the whole dev toolchain (mypy, ruff, pytest, ipython, …). The test stage re-adds it via
# `uv sync --all-groups`, so excluding it here is safe.
RUN uv lock --check && uv sync --locked --no-cache --no-dev --package beetkeeper

ARG RELEASE_TAG=""
ENV RELEASE_TAG=${RELEASE_TAG}
ENTRYPOINT ["beetkeeper"]
CMD ["run"]

# # Test image stage defined below
# `ghcr.io/zach-overflow/beetkeeper:latest` is matched and substituted by Pants with the actual built tag
# of the `//:beetkeeper-server-image` target (added as a dependency of `//:beetkeeper-test-image`).
# Starting from the finished base image means its `COPY` layers are reused, so the test build
# context doesn't need base's source files.
# DL3007: `:latest` here is NOT a mutable upstream pull -- Pants substitutes it with the actual built tag
# of the `//:beetkeeper-server-image` dependency, so the warning doesn't apply.
# hadolint ignore=DL3007
FROM ghcr.io/zach-overflow/beetkeeper:latest AS test

# Install the dev toolchain (pytest/mypy/etc., defined in the workspace-root `dev` group). Skip installing
# the `beetkeeper-plugin` member: its source isn't in this image and the server tests don't import it
# (without this, uv would build a degenerate empty plugin from the lone pyproject).
RUN uv lock --check && uv sync --locked --all-groups --no-cache --no-install-package beetkeeper-plugin
COPY src/python/tests/ /app/src/python/tests
COPY build_scripts/ /app/build_scripts
COPY hooks/ /app/hooks

ENTRYPOINT ["uv"]
CMD ["run", "--all-groups", "pytest", "-vv", "/app/src/python/tests"]
