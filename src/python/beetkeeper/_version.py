"""
Runtime version for the `beetkeeper` distribution (also read by setuptools at wheel-build time).

Pants generates `_scm_version.py` from the git state via the `vcs_version` target (setuptools-scm under
the hood), so Pants-built artifacts carry the real version. The module does not exist on disk, so builds
and runs outside Pants (the uv dev venv) fall back to the dev placeholder.
"""

try:
    from beetkeeper._scm_version import version as __version__
except ImportError:
    __version__ = "0.0.0.dev0"
