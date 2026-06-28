#!/usr/bin/env bash
set -euo pipefail

# Lint the GitHub Actions workflow files with actionlint (https://github.com/rhysd/actionlint).
# Shared by the prek `actionlint` hook and by CI. actionlint is a Go binary (not a python/uv tool), so it
# is used from PATH when present, otherwise a PINNED release is downloaded into a cache dir (once).
# prek passes the changed workflow files as args; with no args (CI) actionlint auto-discovers all of
# `.github/workflows`.

ACTIONLINT_VERSION="1.7.12"

if command -v actionlint >/dev/null 2>&1; then
	actionlint_bin="actionlint"
else
	cache_dir="${XDG_CACHE_HOME:-${HOME}/.cache}/beetkeeper/actionlint-${ACTIONLINT_VERSION}"
	actionlint_bin="${cache_dir}/actionlint"
	if [[ ! -x "${actionlint_bin}" ]]; then
		echo "actionlint not on PATH; downloading pinned v${ACTIONLINT_VERSION} into ${cache_dir} ..." >&2
		mkdir -p "${cache_dir}"
		download_url="https://raw.githubusercontent.com/rhysd/actionlint/v${ACTIONLINT_VERSION}/scripts/download-actionlint.bash"
		curl -fsSL "${download_url}" | bash -s -- "${ACTIONLINT_VERSION}" "${cache_dir}" >/dev/null
	fi
fi

# actionlint runs shellcheck on `run:` blocks when shellcheck is on PATH (it is, via the repo's tooling).
"${actionlint_bin}" -color "$@"
