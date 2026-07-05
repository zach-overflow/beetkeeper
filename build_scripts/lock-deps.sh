#!/usr/bin/env bash
#
# Updates all uv.lock and pantsbuild lockfiles across the entire repo.
set -euo pipefail

uv lock
pants generate-lockfiles
