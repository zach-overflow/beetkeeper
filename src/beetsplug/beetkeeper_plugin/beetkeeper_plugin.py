import logging
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Final

from beets.importer import ImportTask  # pants: no-infer-dep
from beets.library import Album, Item  # pants: no-infer-dep
from beets.plugins import BeetsPlugin  # pants: no-infer-dep
from beetsplug._utils.requests import (  # type: ignore[import-untyped]
    RequestHandler,  # pants: no-infer-dep
    TimeoutAndRetrySession,  # pants: no-infer-dep
)
from requests.auth import AuthBase

if TYPE_CHECKING:
    from beets.importer import ImportSession  # pants: no-infer-dep
    from beets.library import Library  # pants: no-infer-dep
    from beets.plugins import EventType  # pants: no-infer-dep
    from requests import PreparedRequest, Response


_LOGGER_NAME: Final[str] = __name__


class BeetkeeperPlugin(BeetsPlugin):
    """
    Plugin which registers a number of beets event listeners, all of which submit a POST request to the beetkeeper
    server. This allows the server to collect event data without 'peeking' into the beets database.
    https://beets.readthedocs.io/en/stable/dev/plugins/events.html"""

    def __init__(self, beetkeeper_server_url: str, raw_api_token: str | None = None):
        """
        Args:
            beetkeeper_server_url: The base url to reach the beetkeeper server when submitting event-based HTTP requests.
            raw_api_token: Optional beetkeeper API authentication token string.
        """
        self._client = _BeetKeeperClient(url=beetkeeper_server_url, api_token=_APIToken(value=raw_api_token or ""))
        super().__init__("beetkeeper_listener")
        self.register_listener("album_imported", self._on_album_import)
        self.register_listener("album_removed", self._on_album_removed)
        self.register_listener("import_task_files", self._on_import_task_files)
        self.register_listener("item_imported", self._on_item_imported)
        self.register_listener("item_removed", self._on_item_removed)

    @cached_property
    def log(self) -> logging.Logger:
        return logging.getLogger(_LOGGER_NAME)

    def _on_album_import(self, lib: Library, album: Album) -> None:
        self.log.debug("Run listener for 'album_imported' ...")
        self._client.post(event_type="album_imported", event_element=album)

    def _on_album_removed(self, lib: Library, album: Album) -> None:
        self.log.debug("Run listener for 'album_removed' ...")
        self._client.post(event_type="album_removed", event_element=album)

    def _on_import_task_files(self, task: ImportTask, session: ImportSession) -> None:
        self.log.debug("Run listener for 'import_task_files' ...")
        self._client.post(event_type="import_task_files", event_element=task)

    def _on_item_imported(self, lib: Library, item: Item) -> None:
        self.log.debug("Run listener for 'item_imported' ...")
        self._client.post(event_type="item_imported", event_element=item)

    def _on_item_removed(self, item: Item) -> None:
        self.log.debug("Run listener for 'item_removed' ...")
        self._client.post(event_type="item_removed", event_element=item)


class _BeetKeeperClient(RequestHandler):
    """
    Custom `RequestHandler` for submitting beetkeeper API requests to the `/api/events` endpoint.
    See code in `beets.importer.session.ImportSession` to understand why we can't run a long-lived async client.
    """

    _base_path: ClassVar[str] = "/api/events"

    def __init__(self, url: str, api_token: _APIToken):
        self._url = url
        self._api_token = api_token
        super().__init__()

    def create_session(self):
        return TimeoutAndRetrySession(auth=_BkAuth(token=self._api_token), url=self._url)

    def post(self, event_type: EventType, event_element: Album | Item | ImportTask | ImportSession) -> Response:
        """Submits a POST reques to the Beetkeeper server, with a request body containing relevant beets event info."""
        return self.request(
            method="post",
            url=self._base_path + self._url_subpath(event_element=event_element),
            json=_jsonify(event_type=event_type, event_element=event_element),
        )

    def _url_subpath(self, event_element: Album | Item | ImportTask | ImportSession) -> str:
        match event_element:
            case Album():
                return "/album"
            case Item():
                return "/track"
            case _:
                return ""


def _jsonify(event_type: EventType, event_element: Album | Item | ImportTask | ImportSession) -> dict[str, Any]:
    """Returns a JSON-serializable dictionary with the beets event details. Result is used as POST request body."""
    if isinstance(event_element, (Album, Item)):
        return dict(event_type=event_type, beets_field={k: v for k, v in event_element.items()})
    elif isinstance(event_type, ImportTask):
        jsonified_imported_items = []
        if imported_items := event_element.imported_items():
            jsonified_imported_items = [_jsonify(event_type=event_type, event_element=item) for item in imported_items]
        return dict(
            event_type=event_type, choice_flag=event_element.choice_flag, imported_items=jsonified_imported_items
        )
    return dict(event_type=event_type, event_element="unknown")


class _BkAuth(AuthBase):
    """https://requests.readthedocs.io/en/latest/user/authentication/"""

    _token: _APIToken

    def __init__(self, token: _APIToken):
        self._token = token

    def __call__(self, r: PreparedRequest):
        r.headers["Authorization"] = self._token.header_value
        return r


@dataclass(frozen=True)
class _APIToken:
    """Wrapper class for a BeetKeeper API token."""

    value: str = field(repr=False)  # mitigate logging the token accidentally.

    def get_value(self) -> str:
        return self.value

    @property
    def header_value(self) -> str:
        return f"Bearer {self.value}"
