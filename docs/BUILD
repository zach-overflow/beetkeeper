# The `mkdocs` console script (Material theme + mkdocstrings + neoteroi OAD plugins) built from the shared
# `tools-resolve` lockfile. mkdocstrings uses griffe STATIC analysis over `src/python`/`src/beetsplug`
# (configured in mkdocs.yml `paths`), so this binary needs only the mkdocs tools — not the app installed.
#
# `pants run` executes this in the repo workspace (repo root as cwd), so mkdocs sees mkdocs.yml, docs/, and
# the src/ trees at their real paths, and writes ./site. Usage:
#   pants run docs:mkdocs.pex -- build --strict     # strict site build into ./site (used by CI)
#   pants run docs:mkdocs.pex -- serve --dev-addr localhost:8666             # local live-reload preview at http://127.0.0.1:8666/
# (Run it directly rather than via a `run_shell_command` wrapper: the runnable-on-PATH wrapper can't expose
# the plugins' entry points to mkdocs, whereas `pants run` on the pex_binary discovers them correctly.)
pex_binary(
    name="mkdocs-pex",
    script="mkdocs",
    resolve="tools-resolve",
    dependencies=[
        "//3rdparty/tools:tools-requirements#mkdocs",
        "//3rdparty/tools:tools-requirements#mkdocs-material",
        "//3rdparty/tools:tools-requirements#mkdocstrings",
        "//3rdparty/tools:tools-requirements#neoteroi-mkdocs",
    ],
)

# `pants run docs:openapi` — regenerate docs/openapi.json from the app's OpenAPI schema (embedded on the
# REST API page via the Neoteroi OAD plugin). This imports beetkeeper, so it shells out to `uv run` (the
# app's env), unlike the mkdocs binary above which only needs `tools-resolve`.
run_shell_command(name="openapi", command="uv run python build_scripts/dump_openapi.py", workdir="/")
