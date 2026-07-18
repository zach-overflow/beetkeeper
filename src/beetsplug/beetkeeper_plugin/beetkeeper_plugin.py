from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, ClassVar, Final

from beets.importer import ImportSession, ImportTask  # pants: no-infer-dep  noqa: TC002
from beets.library import Album, Item  # pants: no-infer-dep
from beets.plugins import BeetsPlugin, EventType  # pants: no-infer-dep  noqa: TC002
from beetsplug._utils.requests import (  # type: ignore[import-untyped]
    RequestHandler,  # pants: no-infer-dep
    TimeoutAndRetrySession,  # pants: no-infer-dep
)
from confuse import ConfigError  # pants: no-infer-dep
from requests.auth import AuthBase
from requests.exceptions import RequestException

if TYPE_CHECKING:
    from requests import PreparedRequest, Response


_LOGGER_NAME: Final[str] = __name__
_DEFAULT_SERVER_PORT: Final[int] = 8337


def _default_server_url() -> str:
    """The beetkeeper server on this host: `http://127.0.0.1:<port>`.

    The plugin normally runs on the same host (usually the same container) as the beetkeeper server, so
    the default push target is loopback at the port from the beets config's `beetkeeper.server` section
    (the server's own config), falling back to beetkeeper's default port when that section is absent.
    """
    from beets import config as beets_config  # pants: no-infer-dep

    try:
        port = int(beets_config["beetkeeper"]["server"]["port"].get(int))
    except ConfigError:
        port = _DEFAULT_SERVER_PORT
    return f"http://127.0.0.1:{port}"


class BeetkeeperPlugin(BeetsPlugin):
    """
    Plugin which registers a number of beets event listeners, all of which submit a POST request to the beetkeeper
    server. This allows the server to collect event data without 'peeking' into the beets database.
    https://beets.readthedocs.io/en/stable/dev/plugins/events.html

    beets instantiates plugins with no arguments, so all settings come from the plugin's own beets config
    section (`beetkeeper_plugin:`), every key optional:
      * `server_url`: base url of the beetkeeper server to push events to. Defaults to loopback at the
        port from the server's own `beetkeeper.server` config section (see `_default_server_url`).
      * `api_token`: bearer token for the push requests, for servers running with login protection.
    """

    # Must stay a subset of the server's accepted `beetkeeper.api.api_models.APIEventType` values.
    _EVENT_PAYLOAD_KEYS: ClassVar[dict[EventType, str]] = {
        "album_imported": "album",
        "album_removed": "album",
        "import_task_files": "task",
        "item_imported": "item",
        "item_removed": "item",
    }

    def __init__(self) -> None:
        """No-arg (beets instantiates plugins bare); reads `server_url`/`api_token` from `self.config`."""
        super().__init__()
        self.config.add({"server_url": "", "api_token": ""})
        self.config["api_token"].redact = True
        server_url = str(self.config["server_url"].as_str()).strip() or _default_server_url()
        raw_api_token = str(self.config["api_token"].as_str())
        self._client = _BeetKeeperClient(url=server_url.rstrip("/"), api_token=_APIToken(value=raw_api_token))
        for event_type, payload_key in self._EVENT_PAYLOAD_KEYS.items():
            self.register_listener(event_type, partial(self._handle_event, event_type, payload_key))

    @cached_property
    def log(self) -> logging.Logger:
        return logging.getLogger(_LOGGER_NAME)

    def _handle_event(self, event_type: EventType, payload_key: str, **kwargs: Any) -> None:
        """
        The single handler behind every registered listener: posts the event's payload element (identified by
        `payload_key` in the event's keyword arguments) to the beetkeeper server.

        Push failures are logged, never raised: beets propagates listener exceptions into the operation that
        fired the event, so an unreachable beetkeeper server must not break imports/removals themselves.
        """
        self.log.debug(f"Run listener for '{event_type}' ...")
        try:
            self._client.post(event_type=event_type, event_element=kwargs[payload_key])
        except RequestException:
            self.log.warning(f"Failed to push the '{event_type}' event to the beetkeeper server.", exc_info=True)


type _EventElement = Album | Item | ImportTask | ImportSession


class _BkSession(TimeoutAndRetrySession):
    """Beetkeeper-only `SingletonMeta` subclass: keeps our Bearer auth off the session shared by other plugins."""


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

    def create_session(self) -> _BkSession:
        session = _BkSession()
        session.auth = _BkAuth(token=self._api_token)
        return session

    def post(self, event_type: EventType, event_element: _EventElement) -> Response:
        """Submits a POST request to the Beetkeeper server, with a request body containing relevant beets event info."""
        return self.request(
            method="post",
            url=self._construct_request_url(event_element=event_element),
            json=self._jsonify(event_type=event_type, event_element=event_element),
        )

    def _construct_request_url(self, event_element: _EventElement) -> str:
        return self._url + self._base_path + self._url_subpath(event_element=event_element)

    @staticmethod
    def _url_subpath(event_element: _EventElement) -> str:
        match event_element:
            case Album():
                return "/album"
            case Item():
                return "/track"
            case ImportTask():
                return "/filesystem"
            case _:
                return ""

    @classmethod
    def _jsonify(cls, event_type: EventType, event_element: _EventElement) -> dict[str, Any]:
        """
        Returns a JSON-serializable dictionary with the beets event details. Result is used as the POST request body,
        and must stay shape-compatible with the server's `beetkeeper.api.api_models` event-body models.
        """
        body: dict[str, Any] = dict(event_type=event_type, pushed_at=datetime.now(UTC).isoformat())
        if isinstance(event_element, Album):
            body["album_fields"] = _model_fields(event_element)
        elif isinstance(event_element, Item):
            body["track_fields"] = _model_fields(event_element)
        elif isinstance(event_element, ImportTask):
            body["choice_flag"] = event_element.choice_flag
            body["imported_items"] = [
                cls._jsonify(event_type=event_type, event_element=item) for item in event_element.imported_items()
            ]
        else:
            body["event_element"] = "unknown"
        return {k: _to_json_safe(v) for k, v in body.items()}


def _model_fields(event_element: Album | Item) -> dict[str, Any]:
    """
    Builds the model's field dict by key iteration (`Album.items()` returns the album's tracks, not field pairs).
    `None`-valued (unset) fields are omitted so the server-side models' field defaults apply instead.
    """
    return {k: value for k in event_element if (value := event_element[k]) is not None}


def _to_json_safe(value: Any) -> Any:
    """
    Recursively coerces `value` into JSON-serializable primitives, so event bodies never crash request serialization:
    beets stores filesystem paths as `bytes`, import tasks carry `Enum` members, and any type introduced by future
    `event_element` expansion degrades to `str(value)` rather than raising `TypeError` inside `requests`.
    """
    match value:
        case str() | int() | float() | None:
            return value
        case bytes() | bytearray():
            return os.fsdecode(bytes(value))
        case Enum():
            return value.name
        case Mapping():
            return {str(k): _to_json_safe(v) for k, v in value.items()}
        case Sequence() | set() | frozenset():
            return [_to_json_safe(v) for v in value]
        case _:
            return str(value)


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
