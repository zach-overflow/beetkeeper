"""Consistency checks between the shared `tools-resolve` and the beetkeeper distribution's requirements.

A few third-party packages are pinned in two independent places: the beetkeeper distribution's
`src/python/pyproject.toml` (the `beetkeeper-resolve`) and the shared tool resolve's
`3rdparty/tools/tools-resolve-requirements.txt` (the `tools-resolve`, which backs mypy + pytest). Pants
can't single-source a version across resolves, so these tests guard against drift by enforcing each shared
package is pinned to the SAME exact semver in both files. See `pants.toml` `[mypy]`/`[pytest]`.

Why each shared package matters:
- `pydantic`: the `pydantic.mypy` plugin (run from `tools-resolve`) should type-check against the same
  pydantic the app actually runs with.
- `fastapi`: the test suite (run from `tools-resolve`) exercises the app's FastAPI routes, so its FastAPI
  must match the app's — otherwise tests validate a different version's behavior than what ships.

Versions are compared; extras are not. `fastapi` is intentionally `fastapi[standard]` in `tools-resolve`
(the test/tool env wants uvicorn/httpx/etc.) but plain `fastapi` in the app deps, so extras are ignored.
"""

import re
import tomllib
from pathlib import Path
from typing import Final

import pytest

_SHARED_PACKAGES: Final[tuple[str, ...]] = ("pydantic", "fastapi")

# Under Pants' pytest sandbox the test runs in a chroot, not the repo root; `_ROOT_MARKER` anchors
# `_repo_root()` to the dir where both `file` deps are materialized (see this dir's BUILD).
_TOOLS_REQS_RELPATH: Final[str] = "3rdparty/tools/tools-resolve-requirements.txt"
_PYPROJECT_RELPATH: Final[str] = "src/python/pyproject.toml"
_ROOT_MARKER: Final[str] = _TOOLS_REQS_RELPATH

# The leading project name of a requirement string (the part before any extras `[...]` or version specifier).
_REQ_NAME: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _repo_root() -> Path:
    """The repo (or sandbox) root, located by walking up to the directory containing `_ROOT_MARKER`."""
    for parent in Path(__file__).resolve().parents:
        if (parent / _ROOT_MARKER).is_file():
            return parent
    raise RuntimeError(f"Could not locate the root (no `{_ROOT_MARKER}` found above this test).")


def _canonical(name: str) -> str:
    """Canonicalize a project name for comparison (PEP 503: case-insensitive, `_`/`-` equivalent)."""
    return name.lower().replace("_", "-")


def _requirement_is(requirement: str, package: str) -> bool:
    """True if `requirement`'s project name is exactly `package` (e.g. `pydantic`, not `pydantic-settings`)."""
    match = _REQ_NAME.match(requirement.strip())
    return match is not None and _canonical(match.group(1)) == _canonical(package)


def _exact_pin(package: str) -> re.Pattern[str]:
    """A regex matching an exact pin of `package`: optional extras then `==MAJOR.MINOR.PATCH`."""
    return re.compile(rf"^{re.escape(package)}(?:\[[^\]]*\])?>=(\d+\.\d+\.\d+)$")


def _pyproject_requirement(package: str) -> str:
    """The single requirement string for `package` from `src/python/pyproject.toml`'s `[project].dependencies`."""
    pyproject = _repo_root() / _PYPROJECT_RELPATH
    dependencies = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["dependencies"]
    matches = [dep for dep in dependencies if _requirement_is(dep, package)]
    assert len(matches) == 1, f"expected exactly one `{package}` dependency in {pyproject}, found {matches}"
    return matches[0]


def _tools_resolve_requirement(package: str) -> str:
    """The single requirement string for `package` from `3rdparty/tools/tools-resolve-requirements.txt`."""
    reqs_file = _repo_root() / _TOOLS_REQS_RELPATH
    matches = []
    for raw_line in reqs_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line and _requirement_is(line, package):
            matches.append(line)
    assert len(matches) == 1, f"expected exactly one `{package}` requirement in {reqs_file}, found {matches}"
    return matches[0]


def _exact_semver(package: str, requirement: str) -> str:
    """Assert `requirement` pins `package` to an exact semver (extras allowed) and return the `X.Y.Z` version."""
    match = _exact_pin(package).match(requirement.replace(" ", ""))
    assert match is not None, (
        f"`{package}` must be pinned to an exact semver (`{package}==X.Y.Z`, extras optional), got: {requirement!r}"
    )
    return match.group(1)


@pytest.mark.parametrize("package", _SHARED_PACKAGES)
def test_pins_match(package: str) -> None:
    """The package's two exact-semver pins (app dep vs. tools resolve) are equal."""
    pyproject_version = _exact_semver(package, _pyproject_requirement(package))
    tools_version = _exact_semver(package, _tools_resolve_requirement(package))
    assert pyproject_version == tools_version, (
        f"{package} version drift: {_PYPROJECT_RELPATH} pins {pyproject_version}, but "
        f"{_TOOLS_REQS_RELPATH} pins {tools_version}. Update both to match, then regenerate the tools "
        f"lockfile (`pants generate-lockfiles --resolve=tools-resolve`)."
    )
