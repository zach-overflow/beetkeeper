#!/usr/bin/env bash
set -euo pipefail

uv lock --check || {
	echo "❌ uv.lock is out of sync."
	echo "Run './build_scripts/lock-deps.sh'"
	exit 1
}
