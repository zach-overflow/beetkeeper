#!/usr/bin/env bash
#
# Container entrypoint for the manual test server (see build_scripts/run-test-server.sh). Installs the
# checked-in test config (test_beets_conf.yaml) under /test_dirs and generates fake importable FLAC albums under
# /test_dirs/downloads (in-container only, so no host mount needs cleanup), then (if /host_static is
# mounted) swaps the PEX's extracted `beetkeeper/api/static` directory for a symlink to it so host edits
# render live. The whole build_scripts/dev_scripts directory is mounted read-only at /dev_scripts.
set -exuo pipefail

mkdir -p /test_dirs/{beets,downloads,music}

# beets expects the file to be named `config.yaml` inside $BEETSDIR; /dev_scripts is mounted read-only,
# so copy rather than symlink.
cp /dev_scripts/test_beets_conf.yaml /test_dirs/beets/config.yaml

export BEETSDIR=/test_dirs/beets

# The PEX interpreter provides click + mutagen (app deps), so the prep script needs no extra install.
PEX_INTERPRETER=1 /app/beetkeeper.pex /dev_scripts/prep_fake_audio_files.py \
	--dirpath /test_dirs/downloads create

# The import UI (autocomplete + submit) is pinned to /downloads (`_IMPORT_ROOT`), so expose the fake
# albums there.
ln -sfn /test_dirs/downloads /downloads

if [[ -d /host_static ]]; then
	static_dirpath="$(PEX_INTERPRETER=1 /app/beetkeeper.pex -c \
		'from beetkeeper.api.constants import STATIC_DIRPATH; print(STATIC_DIRPATH)')"
	rm -rf "${static_dirpath}"
	ln -s /host_static "${static_dirpath}"
fi

/app/beetkeeper.pex db upgrade
exec /app/beetkeeper.pex run
