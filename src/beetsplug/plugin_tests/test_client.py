import json
from typing import TYPE_CHECKING, Any

import pytest
from beets.importer import Action, ImportSession, ImportTask
from beets.library import Album, Item
from beetsplug.plugin_tests.conftest import FAKE_SERVER_URL

from beetsplug.beetkeeper_plugin.beetkeeper_plugin import _APIToken, _BeetKeeperClient, _BkAuth, _BkSession

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType


@pytest.fixture
def api_token() -> _APIToken:
    return _APIToken(value="s3cret")


@pytest.fixture
def client(api_token: _APIToken) -> _BeetKeeperClient:
    return _BeetKeeperClient(url=FAKE_SERVER_URL, api_token=api_token)


@pytest.fixture
def item() -> Item:
    return Item(id=2, album_id=1, title="fake track", artist="fake artist", path=b"/music/fake track.mp3")


@pytest.fixture
def mock_task(mocker: MockerFixture, item: Item) -> MockType:
    task: MockType = mocker.Mock(spec=ImportTask)
    task.imported_items.return_value = [item]
    task.choice_flag = Action.APPLY
    return task


def test_client_init(client: _BeetKeeperClient, api_token: _APIToken) -> None:
    """The client keeps its url/token, and builds a beetkeeper-only session carrying the token as Bearer auth."""
    assert client._url == FAKE_SERVER_URL
    assert client._api_token is api_token
    session = client.create_session()
    assert isinstance(session, _BkSession)
    assert isinstance(session.auth, _BkAuth)
    assert session.auth._token is api_token


def test_jsonify(client: _BeetKeeperClient, item: Item, mock_task: MockType, mocker: MockerFixture) -> None:
    """Each element kind serializes to its expected, `json.dumps`-safe request-body shape."""
    item_body = client._jsonify(event_type="item_imported", event_element=item)
    assert item_body["event_type"] == "item_imported"
    assert item_body["track_fields"]["title"] == "fake track"
    assert item_body["track_fields"]["artist"] == "fake artist"
    assert item_body["track_fields"]["path"] == "/music/fake track.mp3"
    assert item_body["track_fields"]["album_id"] == 1
    assert "album_fields" not in item_body
    assert item_body["pushed_at"]

    album_body = client._jsonify(event_type="album_imported", event_element=Album(id=1, album="fake album"))
    assert album_body["event_type"] == "album_imported"
    assert album_body["album_fields"]["album"] == "fake album"
    assert album_body["pushed_at"]

    task_body = client._jsonify(event_type="import_task_files", event_element=mock_task)
    assert task_body["event_type"] == "import_task_files"
    assert task_body["choice_flag"] == Action.APPLY.name
    (imported_item_body,) = task_body["imported_items"]
    assert imported_item_body["event_type"] == "import_task_files"
    assert imported_item_body["track_fields"]["title"] == "fake track"

    mock_task.imported_items.return_value = []
    empty_task_body = client._jsonify(event_type="import_task_files", event_element=mock_task)
    assert empty_task_body["imported_items"] == []

    session_body = client._jsonify(event_type="import_begin", event_element=mocker.Mock(spec=ImportSession))
    assert session_body["event_element"] == "unknown"

    for body in (item_body, album_body, task_body, empty_task_body, session_body):
        json.dumps(body)


@pytest.mark.parametrize(
    ("event_element", "expected_subpath"),
    [
        pytest.param(Album(album="fake album"), "/album", id="album"),
        pytest.param(Item(title="fake track"), "/track", id="item"),
        pytest.param(ImportTask, "/filesystem", id="task"),
        pytest.param(None, "", id="other"),
    ],
)
def test_url_subpath(
    event_element: Album | Item | type[ImportTask] | None, expected_subpath: str, mocker: MockerFixture
) -> None:
    element: Any = event_element
    if event_element is ImportTask:
        element = mocker.Mock(spec=ImportTask)
    elif event_element is None:
        element = mocker.Mock(spec=ImportSession)
    assert _BeetKeeperClient._url_subpath(event_element=element) == expected_subpath


def test_post(client: _BeetKeeperClient, item: Item, mocker: MockerFixture) -> None:
    """`post` composes the full endpoint URL and the jsonified body, returning the raw response."""
    mock_request = mocker.patch.object(_BeetKeeperClient, "request")
    response = client.post(event_type="item_imported", event_element=item)
    mock_request.assert_called_once()
    request_kwargs = mock_request.call_args.kwargs
    assert request_kwargs["method"] == "post"
    assert request_kwargs["url"] == f"{FAKE_SERVER_URL}/api/events/track"
    expected_body = client._jsonify(event_type="item_imported", event_element=item)
    assert request_kwargs["json"].keys() == expected_body.keys()
    assert {k: v for k, v in request_kwargs["json"].items() if k != "pushed_at"} == {
        k: v for k, v in expected_body.items() if k != "pushed_at"
    }
    assert response is mock_request.return_value
