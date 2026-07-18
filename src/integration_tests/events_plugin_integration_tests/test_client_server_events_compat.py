"""
Contract-compatibility tests between the beets plugin's events client (`beetsplug.beetkeeper_plugin`)
and the beetkeeper server's `/api/events` routes (`beetkeeper.api.api_routes.events_router`).
"""

from typing import TYPE_CHECKING, Any, cast

import pytest
from beets.importer import Action, ImportTask  # pants: no-infer-dep
from beets.library import Album, Item  # pants: no-infer-dep
from fastapi import status

from beetkeeper.api.api_models import AlbumEventBody, ImportTaskFilesEventBody, TrackEventBody

if TYPE_CHECKING:
    from collections.abc import Callable

    from beets.plugins import EventType  # pants: no-infer-dep
    from pydantic import BaseModel
    from pytest_mock import MockerFixture, MockType

    from beetsplug.beetkeeper_plugin.beetkeeper_plugin import _BeetKeeperClient

type _EventElement = Album | Item | ImportTask
type _ElementFactory = Callable[[type[_EventElement]], _EventElement]


@pytest.fixture
def event_element_factory(mocker: MockerFixture) -> _ElementFactory:
    """
    Factory creating an `_EventElement` instance of the given type. The field values do not matter, so long
    as they conform with the underlying class type and carry the beets db IDs the server models require.
    """

    def _factory(event_element_type: type[_EventElement]) -> _EventElement:
        if event_element_type is Album:
            return Album(id=1, album="fake album")
        if event_element_type is Item:
            return Item(id=2, album_id=1, title="fake track", path=b"/music/fake track.mp3")
        task = mocker.Mock(spec=ImportTask)
        task.imported_items.return_value = [_factory(Item)]
        task.choice_flag = Action.APPLY
        return cast("ImportTask", task)

    return _factory


_EVENT_CASES = [
    pytest.param("album_imported", Album, AlbumEventBody, "/api/events/album", id="album_imported"),
    pytest.param("album_removed", Album, AlbumEventBody, "/api/events/album", id="album_removed"),
    pytest.param("item_imported", Item, TrackEventBody, "/api/events/track", id="item_imported"),
    pytest.param("item_removed", Item, TrackEventBody, "/api/events/track", id="item_removed"),
    pytest.param(
        "import_task_files", ImportTask, ImportTaskFilesEventBody, "/api/events/filesystem", id="import_task_files"
    ),
]


@pytest.mark.parametrize(("event_type", "event_element_type", "events_api_model_type", "_route_path"), _EVENT_CASES)
def test_client_request_data_and_app_request_models_compatible(
    plugin_client: _BeetKeeperClient,
    event_element_factory: _ElementFactory,
    event_type: EventType,
    event_element_type: type[_EventElement],
    events_api_model_type: type[BaseModel],
    _route_path: str,
) -> None:
    """
    Ensures the beetkeeper_plugin's POST request's JSON data is compatible with the
    `beetkeeper.api.api_routes.events_router.events_router` route coroutines / request models.
    """
    request_body = plugin_client._jsonify(
        event_type=event_type, event_element=event_element_factory(event_element_type)
    )
    validated = events_api_model_type.model_validate(request_body)
    assert validated.event_type == event_type  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("event_type", "event_element_type", "_events_api_model_type", "expected_route_path"), _EVENT_CASES
)
def test_client_requests_and_app_event_routes_compatible(
    app_base_url: str,
    plugin_client: _BeetKeeperClient,
    event_element_factory: _ElementFactory,
    event_type: EventType,
    event_element_type: type[_EventElement],
    _events_api_model_type: type[BaseModel],
    expected_route_path: str,
) -> None:
    """
    Ensures that the plugin (client) requests are generally compatible with the app's event routes.
    Mocks any database interactions, to focus purely on fastapi deserialization / serialization and
    contract compatibility.
    """
    event_element = event_element_factory(event_element_type)
    response = plugin_client.post(event_type=event_type, event_element=event_element)
    assert response.status_code == status.HTTP_201_CREATED, (
        f"Expected plugin events client request to succeed, but got {response.status_code}: {response.text}"
    )
    response_body: dict[str, Any] = response.json()
    assert response_body["event_type"] == event_type
    request_mock = cast("MockType", plugin_client.request)
    assert request_mock.call_args.kwargs["url"] == app_base_url + expected_route_path
