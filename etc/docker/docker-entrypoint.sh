#!/usr/bin/env bash
set -euo pipefail

extra_reqs="${EXTRA_PIP_REQS:-}"
if [[ -n ${extra_reqs} ]]; then
	if [[ ! -f ${extra_reqs} ]]; then
		echo "EXTRA_PIP_REQS points at '${extra_reqs}', which does not exist or is not a file" >&2
		exit 1
	fi
	extra_site="/app/extra-site"
	python3.14 -m pip install --no-cache-dir --upgrade --target "${extra_site}" -r "${extra_reqs}"
	# The app is a PEX; PEX_EXTRA_SYS_PATH is the supported way to put extra dists on its sys.path.
	export PEX_EXTRA_SYS_PATH="${extra_site}${PEX_EXTRA_SYS_PATH:+:${PEX_EXTRA_SYS_PATH}}"
fi

exec python3.14 /app/beetkeeper.pex "$@"
