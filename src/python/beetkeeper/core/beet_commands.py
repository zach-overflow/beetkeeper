"""
Defines the logic pertaining to generating `beet` CLI commands from certain FastAPI endpoint request models.

TODO[Claude]: Resolve the core beets-integration architecture before implementing. The integration
    model is currently ambiguous and the two options are mutually exclusive:
      (a) shell out to the `beet` CLI as a subprocess (matches this module's name/docstring), or
      (b) import beets and drive it via its internal Python API (matches the beets dev-docs links in
          CLAUDE.md and `core/__init__.py`).
    Note `beets` is NOT currently a declared dependency in `src/python/pyproject.toml`, which points
    toward (a). Pick one explicitly; if (b), add the dependency. Decide async strategy too: subprocess
    invocation should use anyio (e.g. `anyio.run_process` / `anyio.open_process`), per CLAUDE.md.
TODO[Claude]: Define where the FastAPI request/response schemas referenced here ("from certain FastAPI
    endpoint request models") actually live and standardize it (e.g. a `schemas.py` per domain, or
    Pydantic models co-located with each router). No such models exist yet, so the convention is unset.
"""
