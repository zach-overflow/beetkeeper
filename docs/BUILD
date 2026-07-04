# The `mkdocs` console script (with the Material theme) built from the shared `tools-resolve` lockfile.
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
    dependencies=["//3rdparty/tools:tools-requirements#mkdocs", "//3rdparty/tools:tools-requirements#mkdocs-material"],
)
