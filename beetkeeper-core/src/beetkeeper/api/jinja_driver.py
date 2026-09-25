import json
import logging
from functools import cache
from typing import Any, ClassVar

import jinja2
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from beetkeeper._version import __version__
from beetkeeper.api.constants import STATIC_DIRPATH
from beetkeeper.api.security import SESSION_COOKIE_NAME

_LOGGER = logging.getLogger(__name__)


@jinja2.pass_context
def _relative_url_for(context: dict[str, Any], name: str, /, **path_params: Any) -> str:
    """
    Root-relative replacement for Starlette's default `url_for` template global (which is absolute).

    Absolute URLs bake in the scheme/host the server *believes* it has — wrong behind any TLS-terminating
    reverse proxy whose forwarded headers aren't trusted, at which point browsers block the page's `http://`
    script/CSS/HTMX URLs as mixed content and the whole UI goes dead. Root-relative paths resolve against
    the page's own origin, so URL generation works through any proxy chain (or none) with no
    forwarded-header trust required. Like the default global, this needs `request` in the render context.
    """
    request: Request = context["request"]
    url_path = str(request.app.url_path_for(name, **path_params))
    root_path = request.scope.get("root_path", "").rstrip("/")
    return f"{root_path}{url_path}"


@cache
def _get_latest_available_version_semver() -> str:
    """
    Attempts to determine the latest available version of `beetkeeper` from PyPI. Returns `__version__` on any
    failure to prevent false positives for any 'new version available' user notifications.
    """
    pypi_url = "https://pypi.org/pypi/beetkeeper/json"
    # Default to current in case the latest info cannot be gathered from PyPI. This is to ensure
    # notifications of later version availability are never false positives.
    latest_available_app_version = __version__
    try:
        import httpx

        pypi_pkg_response_json = httpx.get(pypi_url).raise_for_status().json()
        latest_available_app_version = pypi_pkg_response_json["info"]["version"]
    except httpx.HTTPStatusError as e:
        _LOGGER.error(f"Failed to pull version info from {pypi_url}. Got http error code {e.response.status_code}.")
    except KeyError:
        pretty_json = json.dumps(pypi_pkg_response_json, indent=2)
        _LOGGER.error(f"Failed to get version info from PyPI version response JSON from {pypi_url}:\n{pretty_json}")
    except Exception as e:
        _LOGGER.error(f"Unexpected failure during version lookup attempt: {e}")
    return latest_available_app_version


class _TemplatesSingleton:
    _instance: ClassVar[Jinja2Templates | None] = None

    @classmethod
    def load(cls) -> Jinja2Templates:
        """
        Build (once) and return the app's `Jinja2Templates`, rooted at `static/html_templates`.

        Registers the template globals: `url_for` (root-relative, see `_relative_url_for`),
        `current_app_version` (`__version__` without any `+local` suffix), `session_cookie_name`, and
        `latest_available_app_version` (looked up on PyPI once).
        """
        if not cls._instance:
            tpls = Jinja2Templates(directory=STATIC_DIRPATH / "html_templates")
            tpls.env.globals["url_for"] = _relative_url_for
            current_version = __version__
            if "+" in current_version:
                current_version = current_version.split("+")[0]
            tpls.env.globals["current_app_version"] = current_version
            tpls.env.globals["session_cookie_name"] = SESSION_COOKIE_NAME
            tpls.env.globals["latest_available_app_version"] = _get_latest_available_version_semver()
            cls._instance = tpls
        return cls._instance


def get_templates() -> Jinja2Templates:
    """The shared `Jinja2Templates` instance every UI route renders with."""
    return _TemplatesSingleton.load()
