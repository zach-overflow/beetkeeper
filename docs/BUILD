# Run via `pants run docs:mkdocs-pex` directly: a `run_shell_command` wrapper can't expose the plugins'
# entry points to mkdocs, whereas `pants run` on the pex_binary discovers them.
pex_binary(
    name="mkdocs-pex",
    script="mkdocs",
    resolve="tools-resolve",
    dependencies=[
        "//3rdparty/tools:tools-requirements#mkdocs",
        "//3rdparty/tools:tools-requirements#mkdocs-material",
        "//3rdparty/tools:tools-requirements#mkdocs-swagger-ui-tag",
    ],
)
