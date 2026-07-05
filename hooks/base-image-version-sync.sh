#!/usr/bin/env bash
#
# Ensures that the base lscr.io/linuxserver/beets Docker image is built for the same version of `beets`
# as our constraint-dependencies version is set to.
set -euo pipefail

DOCKERFILE_PATH="./Dockerfile"
PYPROJ_PATH="./pyproject.toml"
BASE_BEETS_VERSION=$(sed -rn 's/^FROM[[:space:]]lscr\.io\/linuxserver\/beets:([^ ]+).*$/\1/p' "${DOCKERFILE_PATH}")
PYPROJ_BEETS_CONSTRAINT_VERSION=$(sed -rn 's/^.*beets==([^\"]+).*$/\1/p' "${PYPROJ_PATH}")

if [[ "$BASE_BEETS_VERSION" != "$PYPROJ_BEETS_CONSTRAINT_VERSION" ]]; then
	echo "Detected mismatch between base Docker image's target beets version ('$BASE_BEETS_VERSION') and constraint-dependencies beets version ('$PYPROJ_BEETS_CONSTRAINT_VERSION')."
	exit 1
fi
