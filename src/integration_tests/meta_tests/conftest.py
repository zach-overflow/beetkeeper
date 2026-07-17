from pathlib import Path
from typing import Final

from packaging.requirements import Requirement
import pytest
import tomlkit


_INT_TEST_DIRPATH: Final[Path] = Path(__file__).resolve().parent.parent
_SRC_DIRPATH: Final[Path] = _INT_TEST_DIRPATH.parent
REPO_ROOT: Final[Path] = _SRC_DIRPATH.parent.resolve()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Returns the resolved `Path` to the repo root directory."""
    return Path(REPO_ROOT).resolve()


@pytest.fixture(scope="session")
def bk_pyproject_path() -> Path:
    """Returns the `Path` to the `beetkeeper` distribution's `pyproject.toml` file."""
    return REPO_ROOT / "src" / "python" / "pyproject.toml"


@pytest.fixture(scope="session")
def plugin_pyproject_path() -> Path:
    """Returns the `Path` to the `beetkeeper-plugin` distribution's `pyproject.toml` file."""
    return REPO_ROOT / "src" / "beetsplug" / "pyproject.toml"


@pytest.fixture(scope="session")
def root_pyproject_path() -> Path:
    """Returns the `Path` to the repo's root `pyproject.toml` file."""
    return REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="session")
def bk_pyproject_data(bk_pyproject_path: Path) -> tomlkit.TOMLDocument:
    """Returns the contents of the `beetkeeper` distribution's `pyproject.toml`."""
    return tomlkit.loads(bk_pyproject_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def plugin_pyproject_data(plugin_pyproject_path: Path) -> tomlkit.TOMLDocument:
    """Returns the contents of the `beetkeeper-plugin` distribution's `pyproject.toml`."""
    return tomlkit.loads(plugin_pyproject_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def root_pyproject_data(root_pyproject_path: Path) -> tomlkit.TOMLDocument:
    """Returns the contents of repo's root `pyproject.toml`."""
    return tomlkit.loads(root_pyproject_path.read_text(encoding="utf-8"))


def _get_req_names_to_reqs_dict(
    pyproj_data: tomlkit.TOMLDocument, lookup_keys: list[str] | None = None
) -> dict[str, Requirement]:
    """Helper which returns the list of `Requirement` objects from a given `pyproject.toml` file's data."""
    # if lookup_keys:
    #     import pdb; pdb.set_trace()
    lookup_keys = lookup_keys or ["project", "dependencies"]
    deps_data = pyproj_data
    for lk in lookup_keys:
        deps_data = deps_data[lk]
    reqs = [Requirement(dep) for dep in deps_data]
    return {r.name: r for r in reqs}


@pytest.fixture(scope="session")
def bk_reqs(bk_pyproject_data: tomlkit.TOMLDocument) -> dict[str, Requirement]:
    """Returns the dict of pkg name to `packaging.requirement.Requirement` in `beetkeeper`'s dependencies."""
    return _get_req_names_to_reqs_dict(pyproj_data=bk_pyproject_data)


@pytest.fixture(scope="session")
def plugin_reqs(plugin_pyproject_data: tomlkit.TOMLDocument) -> dict[str, Requirement]:
    """Returns the dict of pkg name to `packaging.requirement.Requirement` in `beetkeeper-plugin`'s dependencies."""
    return _get_req_names_to_reqs_dict(pyproj_data=plugin_pyproject_data)


@pytest.fixture(scope="session")
def root_reqs(root_pyproject_data: tomlkit.TOMLDocument) -> dict[str, Requirement]:
    """Returns the dict of pkg name to `packaging.requirement.Requirement` of root pyproject.toml's dependencies."""
    return _get_req_names_to_reqs_dict(pyproj_data=root_pyproject_data, lookup_keys=["dependency-groups", "dev"])


@pytest.fixture(scope="session")
def tool_resolve_reqs() -> dict[str, Requirement]:
    """Returns the dict of pkg name to `packaging.requirement.Requirement` in `beetkeeper`'s dependencies."""
    tools_reqs_filepath = REPO_ROOT / "3rdparty" / "tools" / "tools-resolve-requirements.txt"
    dep_lines = [
        line.strip()
        for line in tools_reqs_filepath.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    reqs = [Requirement(dep_line) for dep_line in dep_lines]
    return {r.name: r for r in reqs}
