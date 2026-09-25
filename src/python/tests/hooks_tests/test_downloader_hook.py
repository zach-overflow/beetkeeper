"""Tests for `beetkeeper.hooks.DownloaderHook`: the downloader API search, its parsing, and path mapping.

Every request is answered in-process by an `httpx.MockTransport`; nothing touches the network.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from beetkeeper.hooks import DownloaderHook
from beetkeeper.settings import DownloaderHookConfSection

Handler = Callable[[httpx.Request], httpx.Response]


def _config(**overrides: Any) -> DownloaderHookConfSection:
    settings: dict[str, Any] = {
        "base_url": "http://qbit.local:8080",
        "search_endpoint_path": "/api/v2/torrents/info",
        "beet_field_to_dl_search_field": {"album": "name", "albumartist": "artist"},
        "filepath_json_key": "content_path",
        "replace_downloader_paths_prefix": "/data/torrents/complete",
    }
    settings.update(overrides)
    return DownloaderHookConfSection(**settings)


def _hook(handler: Handler, config: DownloaderHookConfSection | None = None) -> DownloaderHook:
    return DownloaderHook(config or _config(), Path("/downloads"), transport=httpx.MockTransport(handler))


def _json(body: Any, status_code: int = 200) -> Handler:
    return lambda _request: httpx.Response(status_code, json=body)


def test_query_params_renames_configured_fields_and_skips_empty_ones() -> None:
    hook = _hook(_json([]))
    entry = {"album": "Geogaddi", "albumartist": "", "year": 2002, "id": 7}
    assert hook.query_params(entry) == {"name": "Geogaddi"}


def test_query_params_stringifies_values() -> None:
    hook = _hook(_json([]), _config(beet_field_to_dl_search_field={"year": "year", "mb_albumid": "mbid"}))
    assert hook.query_params({"year": 2002, "mb_albumid": None}) == {"year": "2002"}


@pytest.mark.anyio
async def test_search_sends_params_and_bearer_token_to_the_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=[{"name": "Geogaddi", "content_path": "/data/torrents/complete/BoC - Geogaddi"}]
        )

    result = await _hook(handler, _config(api_key=SecretStr("s3cret"))).search({"name": "Geogaddi", "artist": "BoC"})

    (request,) = seen
    assert request.method == "GET"
    assert request.url == "http://qbit.local:8080/api/v2/torrents/info?name=Geogaddi&artist=BoC"
    assert request.headers["Authorization"] == "Bearer s3cret"
    assert result.found is True
    assert result.status_code == 200
    assert result.source_path == "/downloads/BoC - Geogaddi"


@pytest.mark.anyio
async def test_search_accepts_a_single_object_response() -> None:
    result = await _hook(_json({"content_path": "/data/torrents/complete/x"})).search({"name": "x"})
    assert result.found is True and result.source_path == "/downloads/x"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("handler", "detail"),
    [
        pytest.param(_json([]), "No search results.", id="empty-list"),
        pytest.param(_json([{"name": "x"}]), "carry no `content_path` field", id="missing-path-key"),
        pytest.param(_json(["not-a-dict"]), "carry no `content_path` field", id="non-object-result"),
        pytest.param(_json([{"content_path": 42}]), "is not a path", id="non-string-path"),
        pytest.param(_json({"error": "nope"}, status_code=500), "Downloader API error", id="http-error"),
        pytest.param(lambda _r: httpx.Response(200, content=b"<html>"), "non-JSON", id="non-json-body"),
    ],
)
async def test_search_reports_unusable_responses_without_raising(handler: Handler, detail: str) -> None:
    result = await _hook(handler).search({"name": "x"})
    assert result.found is False
    assert result.source_path is None
    assert detail in result.detail


@pytest.mark.anyio
async def test_search_reports_a_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = await _hook(handler).search({"name": "x"})
    assert result.found is False
    assert result.status_code is None
    assert "unreachable" in result.detail


@pytest.mark.anyio
async def test_search_without_params_makes_no_request() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    result = await _hook(handler).search({})
    assert result.found is False and "none of the configured fields" in result.detail


@pytest.mark.anyio
async def test_disabled_hook_searches_nothing() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    hook = DownloaderHook(DownloaderHookConfSection(), Path("/downloads"), transport=httpx.MockTransport(handler))
    assert hook.enabled is False
    result = await hook.search({"name": "x"})
    assert result.found is False and "No downloader API is configured" in result.detail


@pytest.mark.parametrize(
    ("prefix", "downloader_path", "expected"),
    [
        pytest.param("/data/torrents/complete", "/data/torrents/complete/Album", "/downloads/Album", id="prefix"),
        pytest.param("/data/torrents/complete/", "/data/torrents/complete/Album", "/downloads/Album", id="slash"),
        pytest.param("", "/downloads/Album", "/downloads/Album", id="no-prefix-same-view"),
        pytest.param("/data/torrents", "/elsewhere/Album", "/elsewhere/Album", id="prefix-absent-unchanged"),
        pytest.param("/data/torrents/complete", "/data/torrents/complete", "/downloads", id="exactly-prefix"),
    ],
)
def test_to_local_path(prefix: str, downloader_path: str, expected: str) -> None:
    hook = _hook(_json([]), _config(replace_downloader_paths_prefix=prefix))
    assert str(hook.to_local_path(downloader_path)) == expected


def test_search_result_json_round_trip() -> None:
    hook = _hook(_json([]))
    result = hook._parse([{"content_path": "/data/torrents/complete/A"}], 200)
    assert json.loads(result.model_dump_json()) == {
        "found": True,
        "status_code": 200,
        "source_path": "/downloads/A",
        "detail": "",
    }
