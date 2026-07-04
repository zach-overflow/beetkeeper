#!/usr/bin/env bash
#
# Run a local beetkeeper container for MANUAL, interactive testing against a temporary COPY of the user's
# beets data (so the host files are never modified). Mounts follow the README's "Docker Installation"
# convention: three host subdirectories are mounted SEPARATELY to the container's /beets, /downloads, and
# /music volumes.
#
# Usage:
#   BEETKEEPER_HOST_TEST_DIRPATH=/path/to/host/dir ./build_scripts/run-test-server.sh
#
# `BEETKEEPER_HOST_TEST_DIRPATH` must point to a directory containing these three subdirectories:
#   beets/      -> mounted at /beets      (beets config + beetkeeper app data); must contain `config.yaml`,
#                  and MAY contain `extra-reqs.txt` (pip requirements installed on startup for 3rd-party
#                  beets plugins).
#   downloads/  -> mounted at /downloads  (raw, un-imported audio to import FROM).
#   music/      -> mounted at /music      (the beets music library; imports land here).
#
# The server is published on http://localhost:8080; press Ctrl-C to stop (the temp copy is then removed).

set -exuo pipefail

if [[ -z "${BEETKEEPER_HOST_TEST_DIRPATH:-}" ]]; then
	echo "Missing required 'BEETKEEPER_HOST_TEST_DIRPATH' environment variable. Cannot run." && exit 1
fi

host_dirpath="${BEETKEEPER_HOST_TEST_DIRPATH}"
for subdir in beets downloads music; do
	if [[ ! -d "${host_dirpath}/${subdir}" ]]; then
		echo "Expected subdirectory '${host_dirpath}/${subdir}' (see this script's header for the required layout). Cannot run." && exit 1
	fi
done
if [[ ! -f "${host_dirpath}/beets/config.yaml" ]]; then
	echo "Expected a beets config at '${host_dirpath}/beets/config.yaml'. Cannot run." && exit 1
fi

# Build from the repo root regardless of where this script is invoked from.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
pants package //:beetkeeper-server-image

cleanup() {
	if [[ -n "${tmp_dirpath:-}" && -d "${tmp_dirpath}" ]]; then
		rm -rf "${tmp_dirpath}"
	fi
}

tmp_dirpath="$(mktemp -d)"
trap cleanup EXIT

# Copy into a temp dir so host files are untouched (APFS copy-on-write keeps the large `downloads/` copy cheap).
cp -R "${host_dirpath}/beets" "${tmp_dirpath}/beets"
cp -R "${host_dirpath}/downloads" "${tmp_dirpath}/downloads"
cp -R "${host_dirpath}/music" "${tmp_dirpath}/music"

# Rewrite the copied beets config to container paths (import from /downloads into /music; db under /beets).
sed -i.bak \
	-e "s|^directory:.*|directory: /music|" \
	-e "s|^library:.*|library: /beets/library.db|" \
	"${tmp_dirpath}/beets/config.yaml"
rm -f "${tmp_dirpath}/beets/config.yaml.bak"

# beetkeeper reads its settings from a top-level `beetkeeper` section of the beets config; paths are container paths.
cat >>"${tmp_dirpath}/beets/config.yaml" <<'EOF'

beetkeeper:
  log_level: INFO
  server:
    hostname: 0.0.0.0
    port: 8080
    server_workers: 1
  database:
    sqlite_path: /beets/beetkeeper.db
EOF

docker_args=(
	--rm
	-e BEETKEEPER_CONFIG=/beets/config.yaml
	-v "${tmp_dirpath}/beets:/beets"
	-v "${tmp_dirpath}/downloads:/downloads"
	-v "${tmp_dirpath}/music:/music"
)
docker run "${docker_args[@]}" ghcr.io/zach-overflow/beetkeeper:latest db upgrade

set +x
echo
echo "beetkeeper test server -> http://localhost:8080"
echo "Temp data (host): ${tmp_dirpath}  (mounted at /beets, /downloads, /music; removed on exit)"
echo "Import albums from these container paths (Import page or POST /api/import):"
find "${tmp_dirpath}/downloads" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; 2>/dev/null | sed 's|^|  /downloads/|' || true
if [[ -f "${tmp_dirpath}/beets/extra-reqs.txt" ]]; then
	echo "Extra beets plugin requirements (installed on startup): ${host_dirpath}/beets/extra-reqs.txt"
fi
echo "Press Ctrl-C to stop."
echo
set -x

# Install any host extra-reqs.txt (3rd-party beets plugins) before launching, in the same `--rm` container.
startup_cmd='set -e
if [ -f /beets/extra-reqs.txt ]; then
	echo "Installing extra beets plugin requirements from /beets/extra-reqs.txt ..."
	uv pip install --system -r /beets/extra-reqs.txt
	cp /beets/originquery.py /usr/local/lib/python3.14/site-packages/beetsplug/
fi
exec beetkeeper run'
docker run -it "${docker_args[@]}" -p 8080:8080 --entrypoint /bin/sh ghcr.io/zach-overflow/beetkeeper:latest -c "${startup_cmd}"
