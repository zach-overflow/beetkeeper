FROM python:3.14-slim-bookworm AS ffmpeg

# Static ffmpeg instead of Debian's package, whose hard deps (SDL, mesa-GL, libllvm15, flite) add ~390 MB of
# GL/video code beets' replaygain never uses. Pinned to an immutable release tag + per-arch SHA256. To bump:
# pick a newer `autobuild-*` tag + stable `n*` from https://github.com/BtbN/FFmpeg-Builds/releases and update
# the tag/version/build + both SHA256s (`sha256sum ffmpeg-<version>-<linux64|linuxarm64>-<build>.tar.xz`).
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
        amd64) btbn_arch="linux64";; \
        arm64) btbn_arch="linuxarm64";; \
        *) echo "unsupported TARGETARCH='${TARGETARCH:-unset}' (need a BuildKit builder)" >&2; exit 1 ;; \
    esac; \
    url="http://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-${btbn_arch}-gpl-8.1.tar.xz"; \
    curl -fsSL "${url}" -o /tmp/ffmpeg.tar.xz; \
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
ARG RELEASE_TAG=""
ENV RELEASE_TAG=${RELEASE_TAG} PEX_ROOT=/app/.pex
ENTRYPOINT ["python3.14", "/app/beetkeeper.pex"]
CMD ["run"]
