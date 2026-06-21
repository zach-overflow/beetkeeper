FROM python:3.14-slim-bookworm AS app

# ghcr.io supported labels found at link below: 
# https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
LABEL org.opencontainers.image.source=https://github.com/zach-overflow/beetkeeper
LABEL org.opencontainers.image.description="A highly configurable, self-hosted app for beets music library management. Supports both automated and manual workflows."
LABEL org.opencontainers.image.licenses=AGPL-3.0-or-later

# https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
# Ensure uv installs in container do not create a virtualenv (since it is not needed in a container)
ENV UV_PROJECT_ENVIRONMENT=/usr/local/
COPY LICENSE.txt pyproject.toml uv.lock ./
# The uv workspace member (the distribution's real `[project]`) must be present for `uv lock --check`.
COPY src/python/pyproject.toml src/python/pyproject.toml
ARG RELEASE_TAG=""
COPY src/python/beetkeeper/ /app/src/python/beetkeeper
RUN uv lock --check && uv sync --locked --no-group dev --no-cache

ENV RELEASE_TAG=${RELEASE_TAG}
ENTRYPOINT ["beetkeeper"]
CMD ["run"]

# # Test image stage defined below
# `beetkeeper-app-image:base` is matched and substituted by Pants with the actual built tag of
# the `//:beetkeeper-app-image` target (added as a dependency of `//:beetkeeper-test-image`).
# Starting from the finished base image means its `COPY` layers are reused, so the test build
# context doesn't need base's source files.
FROM beetkeeper-app-image:app AS test

RUN uv lock --check && uv sync --locked --all-groups --no-cache
COPY src/python/tests/ /app/src/python/tests
COPY build_scripts/ /app/build_scripts
COPY hooks/ /app/hooks

ENTRYPOINT ["uv"]
CMD ["run", "--all-groups", "pytest", "-vv", "/app/src/python/tests"]
