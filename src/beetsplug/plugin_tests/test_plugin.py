from typing import TYPE_CHECKING, Any

import beets
import pytest
from beetsplug.plugin_tests.conftest import FAKE_SERVER_URL
from requests.exceptions import RequestException

from beetsplug.beetkeeper_plugin.beetkeeper_plugin import BeetkeeperPlugin

if TYPE_CHECKING:
    from beets.plugins import EventType  # pants: no-infer-dep
    from pytest_mock import MockerFixture, MockType


def test_listeners_registered(mocker: MockerFixture, mock_client: MockType) -> None:
    """
    One listener per `_EVENT_PAYLOAD_KEYS` entry is registered, each a partial of `_handle_event` bound to that
    entry. Registrations made by the `BeetsPlugin` base class itself (e.g. 'pluginload') are ignored.
    """
    mocked_register_method = mocker.patch.object(BeetkeeperPlugin, "register_listener")
    plugin = BeetkeeperPlugin()
    table_calls = [c for c in mocked_register_method.mock_calls if c.args[0] in BeetkeeperPlugin._EVENT_PAYLOAD_KEYS]
    assert len(table_calls) == len(BeetkeeperPlugin._EVENT_PAYLOAD_KEYS)
    for registration in table_calls:
        event_type, handler = registration.args
        assert handler.func == plugin._handle_event
        assert handler.args == (event_type, BeetkeeperPlugin._EVENT_PAYLOAD_KEYS[event_type])


def test_client_url_from_config(mocker: MockerFixture) -> None:
    """The plugin binds its client to the `server_url` from its own beets config section."""
    mock_client_class = mocker.patch("beetsplug.beetkeeper_plugin.beetkeeper_plugin._BeetKeeperClient", autospec=True)
    BeetkeeperPlugin()
    assert mock_client_class.call_args.kwargs["url"] == FAKE_SERVER_URL


def test_client_url_defaults_to_local_server(mocker: MockerFixture) -> None:
    """Without a configured `server_url`, events target loopback at the `beetkeeper.server.port` port."""
    mock_client_class = mocker.patch("beetsplug.beetkeeper_plugin.beetkeeper_plugin._BeetKeeperClient", autospec=True)
    beets.config["beetkeeper_plugin"]["server_url"].set("")
    beets.config["beetkeeper"]["server"]["port"].set(9999)
    BeetkeeperPlugin()
    assert mock_client_class.call_args.kwargs["url"] == "http://127.0.0.1:9999"


@pytest.mark.parametrize(("event_type", "payload_key"), sorted(BeetkeeperPlugin._EVENT_PAYLOAD_KEYS.items()))
def test_handle_event(
    bk_plugin: BeetkeeperPlugin,
    mock_client: MockType,
    fake_event_kwargs: dict[str, Any],
    event_type: EventType,
    payload_key: str,
) -> None:
    """Each registered event posts exactly its payload element (and only once) to the beetkeeper client."""
    bk_plugin._handle_event(event_type, payload_key, **fake_event_kwargs)
    mock_client.post.assert_called_once_with(event_type=event_type, event_element=fake_event_kwargs[payload_key])


def test_handle_event_push_failure_is_swallowed(
    bk_plugin: BeetkeeperPlugin, mock_client: MockType, fake_event_kwargs: dict[str, Any]
) -> None:
    """An unreachable beetkeeper server must not raise out of the listener (it would break the beets run)."""
    mock_client.post.side_effect = RequestException("server unreachable")
    bk_plugin._handle_event("item_imported", "item", **fake_event_kwargs)
