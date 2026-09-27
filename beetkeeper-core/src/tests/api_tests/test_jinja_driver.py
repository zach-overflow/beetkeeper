"""Unit tests for the PyPI latest-version lookup and the help links in `beetkeeper.api.jinja_driver`."""

import logging
from collections.abc import Iterator
from typing import Final

import httpx
import pytest
from pytest_mock import MockerFixture

from beetkeeper.api import jinja_driver
from beetkeeper.api.jinja_driver import _docs_base_url, _get_latest_available_version_semver, _help_links

_PYPI_URL: Final[str] = "https://pypi.org/pypi/beetkeeper/json"
_CURRENT_VERSION: Final[str] = jinja_driver.__version__


@pytest.fixture(autouse=True)
def _fresh_version_cache() -> Iterator[None]:
    """Clears the `@cache` on the lookup (already populated by the module-level `TEMPLATES` init)."""
    _get_latest_available_version_semver.cache_clear()
    yield
    _get_latest_available_version_semver.cache_clear()


def _http_status_error() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _PYPI_URL)
    response = httpx.Response(httpx.codes.SERVICE_UNAVAILABLE, request=request)
    return httpx.HTTPStatusError("service unavailable", request=request, response=response)


@pytest.mark.parametrize(
    ("mock_exc", "expected_msg", "expected_val"),
    [
        pytest.param(httpx.HTTPStatusError, "Got http error code 503", _CURRENT_VERSION, id="http-error-response"),
        pytest.param(
            KeyError,
            "Failed to get version info from PyPI version response JSON",
            _CURRENT_VERSION,
            id="missing-json-keys",
        ),
        pytest.param(
            RuntimeError, "Unexpected failure during version lookup attempt", _CURRENT_VERSION, id="unexpected-error"
        ),
    ],
)
def test_get_latest_available_version_semver_error_handling(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    mock_exc: type[Exception],
    expected_msg: str,
    expected_val: str,
) -> None:
    """Ensures proper error handling and defaults for the latest version check at template initialization."""
    response_mock = mocker.MagicMock()
    get_mock = mocker.patch("httpx.get", return_value=response_mock)
    if mock_exc is httpx.HTTPStatusError:
        response_mock.raise_for_status.side_effect = _http_status_error()
    elif mock_exc is KeyError:
        response_mock.raise_for_status.return_value.json.return_value = {}
    else:
        get_mock.side_effect = mock_exc("kaboom")

    with caplog.at_level(logging.ERROR, logger=jinja_driver._LOGGER.name):
        result = _get_latest_available_version_semver()

    assert result == expected_val
    assert expected_msg in caplog.text


def test_get_latest_available_version_semver_valid(mocker: MockerFixture) -> None:
    """Ensures latest version lookup works when no issues arise during template setup."""
    response_mock = mocker.MagicMock()
    response_mock.raise_for_status.return_value.json.return_value = {"info": {"version": "99.9.9"}}
    get_mock = mocker.patch("httpx.get", return_value=response_mock)

    assert _get_latest_available_version_semver() == "99.9.9"
    assert _get_latest_available_version_semver() == "99.9.9"
    get_mock.assert_called_once_with(_PYPI_URL)


@pytest.mark.parametrize(
    ("app_version", "expected_url"),
    [
        pytest.param("0.11.1", "https://beetkeeper.dadbodaudio.com/0.11/", id="release-maps-to-its-major-minor"),
        pytest.param("12.3.45", "https://beetkeeper.dadbodaudio.com/12.3/", id="multi-digit-release"),
        pytest.param("0.11.2.dev0", "https://beetkeeper.dadbodaudio.com/latest/", id="dev-build-maps-to-latest"),
        pytest.param("0.0.0.dev0", "https://beetkeeper.dadbodaudio.com/latest/", id="fallback-version-maps-to-latest"),
        pytest.param("1.0.0rc1", "https://beetkeeper.dadbodaudio.com/latest/", id="pre-release-maps-to-latest"),
    ],
)
def test_docs_base_url_follows_the_app_version(app_version: str, expected_url: str) -> None:
    assert _docs_base_url(app_version) == expected_url


def test_help_links_point_at_the_versioned_docs_and_the_issue_forms() -> None:
    assert [help_link["url"] for help_link in _help_links("0.11.1")] == [
        "https://beetkeeper.dadbodaudio.com/0.11/",
        "https://beetkeeper.dadbodaudio.com/0.11/quickstart/",
        "https://beetkeeper.dadbodaudio.com/0.11/configuration/",
        "https://github.com/zach-overflow/beetkeeper/issues/new/choose",
    ]
