shell_sources(name="hooks-scripts")

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
