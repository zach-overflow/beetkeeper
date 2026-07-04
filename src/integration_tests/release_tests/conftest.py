import os
import re
from pathlib import Path
from typing import Final

import pytest
import tomlkit

_RELEASE_TEST_MARKER: Final[str] = "release_tests"

_SRC_PATH: Final[Path] = Path(__file__).resolve().parent.parent.parent
_PLUGIN_PYPROJ_PATH: Final[Path] = _SRC_PATH / "beetsplug" / "pyproject.toml"
_BK_VERSION_DOT_PY_PATH: Final[Path] = _SRC_PATH / "python" / "beetkeeper" / "_version.py"
# The repo-root `VERSION` file is the single source of truth, propagated by hooks/version-sync.sh.
_VERSION_FILE_PATH: Final[Path] = _SRC_PATH.parent / "VERSION"
_BK_VERSION_REGEX: Final[re.Pattern[str]] = re.compile(r"^__version__ = \"([^\"]+)\"\s*$")
# A release tag is exactly `vMAJOR.MINOR.PATCH` (matches the release workflow's publish gate). Anything
# else (a branch, or a pre-release like `v0.0.1-dev`) is not a release we validate the tag against.
_RELEASE_TAG_REGEX: Final[re.Pattern[str]] = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Tag every test in THIS directory with `release_tests`, and skip them unless opted in via the corresponding flag
    (e.g. `pytest -m release_tests`).

    These tests should only run upon a potential release, otherwise they are skipped; pass `-m release_tests` to run.
    NOTE: this hook receives the whole session's items, so we filter to this directory's tests (else we'd skip everything).
    See: https://docs.pytest.org/en/9.0.x/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems
    """
    here = Path(__file__).parent
    opted_in = _RELEASE_TEST_MARKER in (config.getoption("markexpr") or "")
    skip_marker = pytest.mark.skip(reason=f"opt-in release-tests; run with `-m {_RELEASE_TEST_MARKER}`")
    for item in items:
        if here not in item.path.parents:
            continue
        item.add_marker(getattr(pytest.mark, _RELEASE_TEST_MARKER))
        if not opted_in:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def canonical_semver() -> str:
    """The single source-of-truth semver from the repo-root `VERSION` file."""
    return _VERSION_FILE_PATH.read_text(encoding="utf-8").strip()


@pytest.fixture(scope="session")
def beetkeeper_plugin_semver() -> str:
    """
    Returns the statically defined semver version for `beetsplug.beetkeeper_plugin` defined in
    src/beetsplug/pyproject.toml's `version`.
    """
    plugin_pyproj_contents = tomlkit.loads(_PLUGIN_PYPROJ_PATH.read_text())
    return str(plugin_pyproj_contents["project"]["version"])


@pytest.fixture(scope="session")
def beetkeeper_server_semver() -> str:
    """
    Returns the statically defined semver version for `beetkeeper._version` defined in
    `src/python/beetkeeper/_version.py`.

    For example, if `_version.py` contained `__version__ = "0.0.1"`, this would return "0.0.1".
    """
    for line in _BK_VERSION_DOT_PY_PATH.read_text(encoding="utf-8").splitlines():
        if match := _BK_VERSION_REGEX.match(line.strip()):
            return match.group(1).strip()
    raise ValueError(f'Expected a `__version__ = "<semver>"` literal, but none was found in {_BK_VERSION_DOT_PY_PATH}.')


@pytest.fixture(scope="session")
def running_in_github_action() -> bool:
    """
    Returns `True` when the tests are running within a `GitHub Action` environment. False otherwise.
    Used for gating tests which would require git tag inspection.
    """
    # `GITHUB_ACTIONS` is the canonical "am I on a runner" flag (always "true" in Actions), unlike
    # `GITHUB_ACTION` which is the *current action's* id. See:
    # https://docs.github.com/en/actions/reference/workflows-and-actions/variables
    return os.getenv("GITHUB_ACTIONS") == "true"


@pytest.fixture(scope="session")
def github_release_tag_semver(running_in_github_action: bool) -> str | None:
    """
    Returns the `v`-stripped semver of the release tag that triggered this GitHub Actions run, or `None`.

    Resolves the gating the `running_in_github_action` fixture left open: it returns `None` (so the
    version tests self-skip) whenever there is no release tag to validate against — outside GitHub
    Actions, on a non-tag-triggered run (`GITHUB_REF_TYPE != "tag"`), or when the tag is not an exact
    `vMAJOR.MINOR.PATCH` release tag (e.g. a `v0.0.1-dev` pre-release). For a tag of `v0.0.1` it returns
    `"0.0.1"` — the bare semver the wheels + image are versioned with.
    """
    if not running_in_github_action:
        return None
    if os.getenv("GITHUB_REF_TYPE") != "tag":
        return None
    ref_name = os.getenv("GITHUB_REF_NAME", "")
    if not _RELEASE_TAG_REGEX.match(ref_name):
        return None
    return ref_name.removeprefix("v")
