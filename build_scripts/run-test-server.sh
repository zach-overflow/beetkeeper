#!/usr/bin/env bash
#
# Run a local beetkeeper container for MANUAL, interactive testing. Fully self-contained: the container
# entrypoint (build_scripts/dev_scripts/test_container_init.sh) generates throwaway beets/beetkeeper data
# under /test_dirs inside the container, so no host data directory is needed.
#
# The repo's `src/python/beetkeeper/api/static` is mounted read-only at /host_static and symlinked over the
# PEX's extracted copy, so edits to static files (CSS, templates, images) render live on browser refresh.
#
# Usage:
#   ./build_scripts/run-test-server.sh
#
# The server is published on http://localhost:8337; press Ctrl-C to stop.

set -exuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
repo_root="$(pwd)"
pants package //:beetkeeper-server-image

set +x
echo
echo "beetkeeper test server -> http://localhost:8337"
echo "Static files served live from: ${repo_root}/src/python/beetkeeper/api/static"
echo "Press Ctrl-C to stop."
echo
set -x

docker run -it --rm \
	-p 8337:8337 \
	-v "${repo_root}/build_scripts/dev_scripts/test_container_init.sh:/test_container_init.sh:ro" \
	-v "${repo_root}/src/python/beetkeeper/api/static:/host_static:ro" \
	--entrypoint /test_container_init.sh \
	ghcr.io/zach-overflow/beetkeeper:dev
