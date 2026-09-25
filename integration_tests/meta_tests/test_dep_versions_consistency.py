"""
Consistency checks between the shared `tools-resolve`, `beetkeeper`, and the `beetkeeper-plugin` distributions'
requirements.

NOTE: Since `beetkeeper` and `beetkeeper-plugin` are distributions, we only check that the dependency ranges
match for any dependencies common between the two. This will change if we switch to a docker-only approach.
"""

from copy import deepcopy
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from packaging.requirements import Requirement


def test_distributions_overlapping_deps_match(
    bk_reqs: dict[str, Requirement], plugin_reqs: dict[str, Requirement]
) -> None:
    """
    Ensures the overlapping dependencies set within the `beetkeeper-plugin` and the `beetkeeper` distributions' pyproject.toml
    files match.
    """
    bk_req_names = set(bk_reqs.keys())
    plugin_req_names = set(plugin_reqs.keys())
    overlapping_req_names = bk_req_names.intersection(plugin_req_names)
    # maps from req name to a subdict where the keys are the source project name, and the values are their full requirement string.
    mismatches: dict[str, dict[str, str]] = dict()
    for name in overlapping_req_names:
        bk_req = bk_reqs[name]
        plg_req = plugin_reqs[name]
        if plg_req != bk_req:
            mismatches[name] = {"beetkeeper": str(bk_req), "beetkeeper-plugin": str(plg_req)}

    assert len(mismatches) == 0, (
        f"Mismatched dependencie(s) found between beetkeeper and beetkeeper-plugin:\n{json.dumps(mismatches, indent=2)}"
    )


@pytest.mark.parametrize(
    "reqs_fixture_name",
    [
        pytest.param("bk_reqs", id="beetkeeper"),
        pytest.param("plugin_reqs", id="beetkeeper-plugin"),
        pytest.param("root_reqs", id="root-pyproject"),
    ],
)
def test_tool_resolve_and_distro_deps_match(
    request: pytest.FixtureRequest, tool_resolve_reqs: dict[str, Requirement], reqs_fixture_name: str
) -> None:
    """
    Ensures that overlap between deps in `3rdparty/tools/tools-resolve-requirements.txt` and the various pyproject.toml files
    match. The reqs should not be hard pinned since we publish beetkeeper and beetkeeper-plugin as distributions
    which need to be flexible to the downstream user's venvs.
    """

    def _remove_extras(r: Requirement) -> Requirement:
        """We don't care about `extras` when it comes to tool resolve matching."""
        if r.extras:
            r_copy = deepcopy(r)
            r_copy.extras = set()
            return r_copy
        return r

    # get the `id` of the given `pytest.param`
    test_case_id = request.node.callspec.id
    pyproj_reqs: dict[str, Requirement] = request.getfixturevalue(reqs_fixture_name)
    pyproj_req_names = set(pyproj_reqs.keys())
    tool_req_names = set(tool_resolve_reqs.keys())
    overlapping_req_names = tool_req_names.intersection(pyproj_req_names)
    # maps from req name to a subdict where the keys are the source project name, and the values are their full requirement string.
    mismatches: dict[str, dict[str, str]] = dict()
    for name in overlapping_req_names:
        tool_req = _remove_extras(tool_resolve_reqs[name])
        pyproj_req = _remove_extras(pyproj_reqs[name])
        if tool_req != pyproj_req:
            mismatches[name] = {"tools-resolve": str(tool_req), test_case_id: str(pyproj_req)}

    assert len(mismatches) == 0, (
        f"Mismatched dependencie(s) found between tools-resolve and {test_case_id}:\n{json.dumps(mismatches, indent=2)}"
    )
