#!/usr/bin/env bash
#
# Container entrypoint for the manual test server (see build_scripts/run-test-server.sh). Generates a
# self-contained beets/beetkeeper config under /test_dirs, then (if /host_static is mounted) swaps the
# PEX's extracted `beetkeeper/api/static` directory for a symlink to it so host edits render live.
set -exuo pipefail

mkdir -p /test_dirs/{beets,downloads,music}

cat >"/test_dirs/beets/config.yaml" <<'EOF'
directory: /test_dirs/music
library: /test_dirs/beets/library.blb

beetkeeper:
  log_level: INFO
  server:
    hostname: 0.0.0.0
    port: 8337
    server_workers: 1
  database:
    sqlite_path: /test_dirs/beets/beetkeeper.db
EOF

export BEETSDIR=/test_dirs/beets

if [[ -d /host_static ]]; then
	static_dirpath="$(PEX_INTERPRETER=1 /app/beetkeeper.pex -c \
		'from beetkeeper.api.constants import STATIC_DIRPATH; print(STATIC_DIRPATH)')"
	rm -rf "${static_dirpath}"
	ln -s /host_static "${static_dirpath}"
fi

/app/beetkeeper.pex db upgrade
exec /app/beetkeeper.pex run
