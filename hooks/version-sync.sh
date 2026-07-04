#!/usr/bin/env bash
# Propagate `VERSION` (repo root, single source of truth) into the two sites that must agree with it:
#   * src/python/beetkeeper/_version.py -> `__version__`        (beetkeeper wheel + Docker image)
#   * src/beetsplug/pyproject.toml      -> `[project].version` (beetkeeper-plugin wheel)
# No args writes both sites then `uv lock`; `--check` verifies and exits non-zero on drift.
#
# `--check` runs in Pants' `test_cmd` sandbox with only bash + uv (no coreutils), so its code path is pure
# bash; the WRITE path is developer-run with a full shell (sed/mktemp/mv).
set -euo pipefail

script_dir="${BASH_SOURCE[0]%/*}"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
server_py="${repo_root}/src/python/beetkeeper/_version.py"
plugin_toml="${repo_root}/src/beetsplug/pyproject.toml"

canonical="$(<"${repo_root}/VERSION")"
canonical="${canonical//[$' \t\r\n']/}" # strip whitespace (pure-bash; no `tr`)
if [[ -z "${canonical}" ]]; then
	echo "❌ ${repo_root}/VERSION is empty; it must hold a single semver (e.g. 0.0.1)." >&2
	exit 1
fi

# Extract the quoted value from the single `<prefix> = "<value>"` line (pure bash; no `sed`).
extract() { # <file> <ERE-with-one-capture-group>
	local line re="$2"
	while IFS= read -r line || [[ -n "${line}" ]]; do
		if [[ "${line}" =~ $re ]]; then
			printf '%s' "${BASH_REMATCH[1]}"
			return 0
		fi
	done <"$1"
	return 0 # not found -> empty output; the caller reports the drift
}

if [[ "${1:-}" == "--check" ]]; then
	status=0
	server_have="$(extract "${server_py}" '^__version__ = "(.*)"$')"
	plugin_have="$(extract "${plugin_toml}" '^version = "(.*)"$')"
	if [[ "${server_have}" != "${canonical}" ]]; then
		echo "❌ ${server_py} (${server_have:-unset}) != VERSION (${canonical}); run hooks/version-sync.sh" >&2
		status=1
	fi
	if [[ "${plugin_have}" != "${canonical}" ]]; then
		echo "❌ ${plugin_toml} (${plugin_have:-unset}) != VERSION (${canonical}); run hooks/version-sync.sh" >&2
		status=1
	fi
	if [[ "${status}" -eq 0 ]]; then
		echo "✅ version sync OK (${canonical})"
	fi
	exit "${status}"
fi

# WRITE mode (developer-run, full shell available): rewrite each version line, then re-lock.
sub() { # <sed-expr> <file>, portable in-place edit across GNU/BSD sed
	local tmp
	tmp="$(mktemp)"
	sed -E "${1}" "${2}" >"${tmp}" && mv "${tmp}" "${2}"
}
sub "s/^__version__ = \".*\"/__version__ = \"${canonical}\"/" "${server_py}"
sub "s/^version = \".*\"/version = \"${canonical}\"/" "${plugin_toml}"
uv lock
echo "✅ propagated ${canonical} -> _version.py + plugin pyproject (+ uv lock)"
