# These meta tests read repo source files (the two resolves' requirement specs) rather than importing
# beetkeeper, so they declare those files as deps to materialize them into the Pants pytest sandbox.
# Overriding `dependencies` here replaces the parent `__defaults__` (base-pytest-utils), which these
# tests don't need. `file` targets keep their full repo path in the sandbox, so the on-disk layout the
# tests walk (`3rdparty/tools/...`, `src/python/pyproject.toml`) is reproduced.
python_tests(dependencies=["//src/python:dist-pyproject", "//3rdparty/tools:tools-resolve-requirements-file"])
