shell_sources(name="hooks-scripts")

# `test_cmd` doesn't materialize the hook script itself, so depend on its `hooks-scripts` target.
test_cmd(
    name="uv-lockfile-check",
    command="./hooks/uv-lockfile-check.sh",
    execution_dependencies=["//hooks/uv-lockfile-check.sh:hooks-scripts"],
)

# Builtin deps already materialize `_version.py` + plugin pyproject; add the VERSION file + hook script.
test_cmd(
    name="version-sync-check",
    command="./hooks/version-sync.sh --check",
    execution_dependencies=["//:version-file", "//hooks/version-sync.sh:hooks-scripts"],
)

# Ensures our base `linuxserver/beets`` Docker image's beets version matches our pinned `beets` version constraint.
test_cmd(
    name="base-image-version-sync-check",
    command="./hooks/base-image-version-sync.sh",
    execution_dependencies=["//hooks/base-image-version-sync.sh:hooks-scripts", "//:dockerfile", "//:pyproject"],
    extra_tools=["sed"],
)
