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

# mike shells out to a bare `mkdocs` subprocess, so it must run as a venv pex with the venv's `bin/`
# prepended to PATH — otherwise it picks up whatever `mkdocs` (if any) is on the caller's PATH.
pex_binary(
    name="mike-pex",
    script="mike",
    resolve="tools-resolve",
    execution_mode="venv",
    extra_build_args=["--venv=prepend"],
    dependencies=[
        "//3rdparty/tools:tools-requirements#mike",
        "//3rdparty/tools:tools-requirements#mkdocs",
        "//3rdparty/tools:tools-requirements#mkdocs-material",
        "//3rdparty/tools:tools-requirements#mkdocs-swagger-ui-tag",
    ],
)
