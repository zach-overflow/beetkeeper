#!/usr/bin/env bash

set -exuo pipefail

# TODO: add `check` goal to this command if we ever want to use some pants-managed type-checker (mypy is garbage in pants when needing pydantic.mypy)
pants update-build-files --check lint test ::

# Wrap our mypy hook in a `shell_command` so pants can run mypy without us needing to set up an
# entire separate tool resolve just to enable the pydantic mypy plugin.
# https://www.pantsbuild.org/stable/docs/python/goals/check#add-a-third-party-plugin
pants run //hooks:run-mypy
pants run //hooks:run-bandit
