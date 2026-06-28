shell_sources(name="hooks-scripts")


# Wraps the `uv lock --check` command as a testable target. The `test_cmd` builtins don't materialize the
# hook script itself, so (like mypy/bandit below) depend on its per-file `hooks-scripts` target.
test_cmd(
    name="uv-lockfile-check",
    command="./hooks/uv-lockfile-check.sh",
    execution_dependencies=["//hooks/uv-lockfile-check.sh:hooks-scripts"],
)

# Verify the canonical `VERSION` has been propagated into both distributions' committed version fields.
# Builtin test_cmd deps already materialize `_version.py` (lib-source-files) and the plugin pyproject;
# add the VERSION file + the hook script itself.
test_cmd(
    name="version-sync-check",
    command="./hooks/version-sync.sh --check",
    execution_dependencies=["//:version-file", "//hooks/version-sync.sh:hooks-scripts"],
)

# Wrap our mypy hook in a `shell_command` so pants can run mypy without us needing to set up an
# entire separate tool resolve just to enable the pydantic mypy plugin.
# https://www.pantsbuild.org/stable/docs/python/goals/check#add-a-third-party-plugin
test_cmd(
    # NOTE: we don't strictly need `//:pytest`, but use this to order the operations of tests for clearer outputs.
    name="mypy",
    command="./hooks/mypy.sh",
    execution_dependencies=["//:pytest", "//hooks/mypy.sh:hooks-scripts"],
)

# Wrap bandit for similar reasons
test_cmd(
    name="bandit",
    command="./hooks/bandit.sh",
    # NOTE: we don't strictly need `:mypy` here, but use this to order the operations of tests for clearer outputs.
    execution_dependencies=[":mypy", "//hooks/bandit.sh:hooks-scripts"],
)
