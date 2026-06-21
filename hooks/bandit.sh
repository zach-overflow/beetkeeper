#!/usr/bin/env bash
set -euo pipefail

targets=("$@")
if [ "${#targets[@]}" -eq 0 ]; then
	targets=(.)
fi

uv run --all-groups --frozen bandit -c pyproject.toml -r --severity-level all -n 1 "${targets[@]}" || {
	echo "❌ Failed bandit security checks."
	exit 1
}
