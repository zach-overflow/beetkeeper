"""
Integration tooling for downloader clients which offer a REST API. This may be used by `beetkeeper` to fill in any
missing source (pre-import) associative data the application needs for specific operations, such as fresh import retries.

The search contract is deliberately generic so any downloader can be wired up through config alone
(`beetkeeper.settings.DownloaderHookConfSection`): a GET to `search_endpoint_path` with the library entry's
fields as query params, answered with a JSON list of result objects (or a single object), each holding the
download's path under `filepath_json_key`. Only the first result is used.

This package must not import `beetkeeper.api` (the API layer depends on it; see `api.dependencies`).
"""

import logging
from collections.abc import Generator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

if TYPE_CHECKING:
    from beetkeeper.settings import DownloaderHookConfSection

_LOGGER = logging.getLogger(__name__)


class DownloaderSearchResult(BaseModel):
    """Outcome of one downloader search: the local source path when found, else `detail` says why not."""

    model_config = ConfigDict(frozen=True)
    found: bool
    status_code: int | None = None
    source_path: str | None = None
    detail: str = ""


class DownloaderHookAuth(httpx.Auth):
    """Helper for injecting the auth token into the outgoing request headers."""

    def __init__(self, api_token: SecretStr) -> None:
        """Bind the token; it is only revealed when a request is sent."""
        self._token = api_token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        """Attach the Bearer token to the outgoing request."""
        request.headers["Authorization"] = f"Bearer {self._token.get_secret_value()}"
        yield request


class DownloaderHook(httpx.AsyncClient):
    """Specialized async HTTP client for the downloader's REST API, if configured by the user.

    A hook built from a config without `base_url` is *disabled*: `search` answers "not found" without any
    I/O, so callers need not special-case the unconfigured state. Extra keyword arguments reach
    `httpx.AsyncClient` (tests pass a `transport`).
    """

    def __init__(self, config: DownloaderHookConfSection, downloads_path: Path, **client_kwargs: Any) -> None:
        """Bind the client to the configured downloader API and beetkeeper's local downloads root."""
        super().__init__(
            base_url=str(config.base_url) if config.base_url is not None else "",
            auth=DownloaderHookAuth(config.api_key) if config.api_key else None,
            **client_kwargs,
        )
        self._config = config
        self._downloads_path = downloads_path

    @property
    def config(self) -> DownloaderHookConfSection:
        """The user-config settings for the downloader hook."""
        return self._config

    @property
    def enabled(self) -> bool:
        """Whether a downloader API is configured (else `search` is a no-op)."""
        return self._config.enabled

    def query_params(self, entry: Mapping[str, Any]) -> dict[str, str]:
        """The search query params for a library entry: its configured fields, renamed to the API's names.

        Fields the entry lacks, or holds empty, are left out; a lookup with no params is pointless, so
        `search` refuses it.
        """
        params: dict[str, str] = {}
        for field, param in self._config.beet_field_to_dl_search_field.items():
            value = entry.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            params[param] = str(value)
        return params

    async def search(self, params: Mapping[str, str]) -> DownloaderSearchResult:
        """Ask the downloader for the download matching `params`; never raises for API/network failures."""
        if not self.enabled:
            return DownloaderSearchResult(found=False, detail="No downloader API is configured.")
        if not params:
            return DownloaderSearchResult(found=False, detail="The library entry has none of the configured fields.")
        _LOGGER.debug(f"Sending GET search request via downloader hook with params: {dict(params)}")
        try:
            response = await self.get(self._config.search_endpoint_path or "", params=dict(params))
            raw_json = response.raise_for_status().json()
        except httpx.HTTPStatusError as exc:
            _LOGGER.error(f"Downloader hook search request failed: {exc}")
            return DownloaderSearchResult(
                found=False, status_code=exc.response.status_code, detail=f"Downloader API error: {exc}"
            )
        except httpx.HTTPError as exc:
            _LOGGER.error(f"Downloader hook search request failed: {exc}")
            return DownloaderSearchResult(found=False, detail=f"Downloader API unreachable: {exc}")
        except ValueError as exc:
            _LOGGER.error(f"Downloader hook search result JSON unparseable: {exc}")
            return DownloaderSearchResult(
                found=False, status_code=response.status_code, detail="Downloader API returned a non-JSON response."
            )
        return self._parse(raw_json, response.status_code)

    def _parse(self, raw_json: Any, status_code: int) -> DownloaderSearchResult:
        results = raw_json if isinstance(raw_json, list) else [raw_json]
        if not results:
            return DownloaderSearchResult(found=False, status_code=status_code, detail="No search results.")
        top_result = results[0]
        key = self._config.filepath_json_key or ""
        if not isinstance(top_result, dict) or key not in top_result:
            return DownloaderSearchResult(
                found=False, status_code=status_code, detail=f"Search results carry no `{key}` field."
            )
        downloader_path = top_result[key]
        if not isinstance(downloader_path, str) or not downloader_path:
            return DownloaderSearchResult(
                found=False, status_code=status_code, detail=f"Search result `{key}` is not a path."
            )
        return DownloaderSearchResult(
            found=True, status_code=status_code, source_path=str(self.to_local_path(downloader_path))
        )

    def to_local_path(self, downloader_path: str) -> Path:
        """Map a path as the downloader reports it onto beetkeeper's `downloads_path` (see the config docs).

        With no `replace_downloader_paths_prefix` both sides share a filesystem view, so the path is used
        as-is; a path that does not carry the configured prefix is also returned unchanged.
        """
        prefix = self._config.replace_downloader_paths_prefix.rstrip("/")
        if not prefix or not downloader_path.startswith(prefix):
            return Path(downloader_path)
        return self._downloads_path / downloader_path.removeprefix(prefix).lstrip("/")
