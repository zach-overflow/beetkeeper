#!/usr/bin/env bash
#
set -euo pipefail

TGT_UV_PATH="$(uv python list --only-installed --managed-python --output-format json | jq -r '.[0].path')"
mv $TGT_UV_PATH /usr/bin/python
uv pip install --system pex
pex -v ./beetkeeper-0.0.3-py3-none-any.whl --entry-point beetkeeper.main:cli -o beetkeeper.pex
