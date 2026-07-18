from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Final

import beets
import pytest

from beetsplug.beetkeeper_plugin.beetkeeper_plugin import BeetkeeperPlugin

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType

FAKE_SERVER_URL: Final[str] = "http://localhost:8337"


@pytest.fixture(autouse=True)
def plugin_config_section() -> Iterator[None]:
    """Sets the plugin's beets config section (beets instantiates plugins no-arg; settings come from config)."""
    beets.config["beetkeeper_plugin"]["server_url"].set(FAKE_SERVER_URL)
    yield


@pytest.fixture
def mock_client(mocker: MockerFixture) -> MockType:
    """The mocked `_BeetKeeperClient` instance that the plugin under test binds as its `_client`."""
    mock_client_class = mocker.patch("beetsplug.beetkeeper_plugin.beetkeeper_plugin._BeetKeeperClient", autospec=True)
    mock_client_instance: MockType = mock_client_class.return_value
    mock_client_instance.post.return_value = None
    return mock_client_instance


@pytest.fixture
def bk_plugin(mock_client: MockType) -> BeetkeeperPlugin:
    """Returns a real `BeetkeeperPlugin` instance, with its `_BeetKeeperClient` attribute mocked out."""
    return BeetkeeperPlugin()


@pytest.fixture(scope="session")
def fake_event_kwargs() -> dict[str, Any]:
    """
    Fake keywords and placeholder values. These come from the args for different event listener signatures in the beets
    listener docs: https://beets.readthedocs.io/en/stable/dev/plugins/events.html
    """
    return {
        "album": "fake_album",
        "data": {"fake": "data"},
        "destination": "/fake/path/dst",
        "info": "fake_track_info",
        "item": "fake_item",
        "lib": "fake_lib",
        "match": "fake_album_match",
        "model": "fake_model",
        "session": "fake_import_session",
        "source": "/fake/path/src",
        "tags": {"foo": "bar"},
        "task": "fake_task",
    }
