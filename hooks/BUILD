shell_sources(name="hooks-scripts")

# `test_cmd` doesn't materialize the hook script itself, so depend on its `hooks-scripts` target.
test_cmd(
    name="uv-lockfile-check",
    command="./hooks/uv-lockfile-check.sh",
    execution_dependencies=["//hooks/uv-lockfile-check.sh:hooks-scripts"],
)
