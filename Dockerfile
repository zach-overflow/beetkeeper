FROM python:3.14-slim-bookworm AS ffmpeg

# Static ffmpeg instead of Debian's package, whose hard deps (SDL, mesa-GL, libllvm15, flite) add ~390 MB of
# GL/video code beets' replaygain never uses. Pinned to an immutable release tag + per-arch SHA256. To bump:
# pick a newer `autobuild-*` tag + stable `n*` from https://github.com/BtbN/FFmpeg-Builds/releases and update
# the tag/version/build + both SHA256s (`sha256sum ffmpeg-<version>-<linux64|linuxarm64>-<build>.tar.xz`).
ENV FFMPEG_TAG=autobuild-2026-06-27-13-21 \
	FFMPEG_VERSION=n8.1.2 \
	FFMPEG_BUILD=gpl-8.1 \
	FFMPEG_SHA256_AMD64=1fa7d66a8bc3cd5f7b340e365d274106f182ea14269851230c83e4f69a57fc65 \
	FFMPEG_SHA256_ARM64=9c31feb2fb0bb87eafb9432f58e7ef06ca47269f281aefbdaeadfdf57b5c585e
# Throwaway fetch-only stage, so pinning apt versions has no benefit; DL3008 ignored.
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

FROM python:3.14-slim-bookworm AS app

# ghcr.io supported labels found at link below:
# https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
LABEL org.opencontainers.image.source="https://github.com/zach-overflow/beetkeeper" \
	org.opencontainers.image.description="A highly configurable, self-hosted app for beets music library management. Supports both automated and manual workflows." \
	org.opencontainers.image.licenses="AGPL-3.0-or-later"

# Static ffmpeg from the `ffmpeg` stage (beets' replaygain backend); no apt needed in this image.
COPY --from=ffmpeg /usr/local/bin/ffmpeg /usr/local/bin/
WORKDIR /app

# The thin, single-arch PEX for this image's arch (`//:beetkeeper-linux-<arch>`), placed at the build-context root by
# Pants. TARGETARCH is amd64/arm64; each PEX carries only that arch's wheels.
ARG TARGETARCH
COPY beetkeeper-linux-${TARGETARCH}.pex /app/beetkeeper.pex
# Bake the PEX's dependency extraction into an image layer so the first container start isn't slow. `--help`
# exercises the entrypoint without starting the server; `inherit_path="fallback"` lets a derived image add
# beets plugins via `pip install` into this interpreter and have the PEX pick them up.
ENV PEX_ROOT=/app/.pex
RUN python3.14 /app/beetkeeper.pex --help > /dev/null

ARG RELEASE_TAG=""
ENV RELEASE_TAG=${RELEASE_TAG}
ENTRYPOINT ["python3.14", "/app/beetkeeper.pex"]
CMD ["run"]
