from typing import get_args

import pytest
from beets.plugins import EventType

from beetkeeper.constants import BeetsEventType
from beetsplug.beetkeeper_plugin.beetkeeper_plugin import BeetkeeperPlugin


@pytest.fixture(scope="module")
def beetkeeper_api_event_types() -> tuple[str, ...]:
    return tuple(sorted(et.value for et in BeetsEventType))


@pytest.fixture(scope="module")
def plugin_event_types() -> tuple[str, ...]:
    return tuple(sorted(BeetkeeperPlugin._EVENT_PAYLOAD_KEYS.keys()))


@pytest.fixture(scope="module")
def beets_event_types() -> set[str]:
    return set(get_args(EventType))


def test_event_types_match_between_beetkeeper_components(
    beetkeeper_api_event_types: tuple[str, ...], plugin_event_types: tuple[str, ...]
) -> None:
    """
    Ensures the `beetkeeper_plugin.BeetKeeperPlugin._EVENT_PAYLOAD_KEYS` and the
    `beetkeeper.constants.BeetsEventType` enum members are equivalent. The two describe which events each component
    expects to be supported.
    """
    assert beetkeeper_api_event_types == plugin_event_types


@pytest.mark.parametrize(
    "bk_fixture_name",
    [
        pytest.param("beetkeeper_api_event_types", id="beetkeeper"),
        pytest.param("plugin_event_types", id="beetkeeper-plugin"),
    ],
)
def test_event_types_consistent_with_beets(
    request: pytest.FixtureRequest, beets_event_types: set[str], bk_fixture_name: str
) -> None:
    """
    Ensures the `beetkeeper_plugin.BeetKeeperPlugin._EVENT_PAYLOAD_KEYS` /
    `beetkeeper.constants.BeetsEventType` are valid subsets of `beets.plugins.EventType` literals.
    If this fails, it indicates that one or more `beetkeeper` / `beetkeeper_plugin` components are not compliant with
    beets' `beets.plugins.EventType` literals, and the beetkeeper event API may fail to collect event history data.
    """
    test_case_id = request.node.callspec.id
    bk_event_types = set(request.getfixturevalue(bk_fixture_name))
    assert bk_event_types.issubset(beets_event_types), (
        f"{test_case_id} event types must be a subset of the official `beets.plugins.EventTypes` literals."
    )
