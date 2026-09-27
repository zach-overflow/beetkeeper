import json
import logging
import re
from functools import cache
from typing import Any, ClassVar, Final

import jinja2
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from beetkeeper._version import __version__
from beetkeeper.api.constants import STATIC_DIRPATH
from beetkeeper.api.security import SESSION_COOKIE_NAME

_LOGGER = logging.getLogger(__name__)

_DOCS_SITE_URL: Final[str] = "https://beetkeeper.dadbodaudio.com"
_NEW_ISSUE_URL: Final[str] = "https://github.com/zach-overflow/beetkeeper/issues/new/choose"
_RELEASE_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?P<major_minor>\d+\.\d+)\.\d+")


def _docs_base_url(app_version: str) -> str:
    """
    The root of the published docs matching `app_version`. The docs site is versioned per app
    MAJOR.MINOR, so an exact release maps to its own docs; anything else (a dev build, whose MAJOR.MINOR
    may not be published yet) maps to the `latest` alias.
    """
    release_match = _RELEASE_VERSION_PATTERN.fullmatch(app_version)
    docs_version = release_match["major_minor"] if release_match else "latest"
    return f"{_DOCS_SITE_URL}/{docs_version}/"


def _help_links(app_version: str) -> list[dict[str, str]]:
    """The rows of the help dialog in `base_template.html`, in display order."""
    docs_base_url = _docs_base_url(app_version)
    return [
        {"topic": "Documentation", "url": docs_base_url},
        {"topic": "Getting started", "url": f"{docs_base_url}quickstart/"},
        {"topic": "Configuration", "url": f"{docs_base_url}configuration/"},
        {"topic": "Submit a feature request / Report a bug", "url": _NEW_ISSUE_URL},
    ]


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
        `current_app_version` (`__version__` without any `+local` suffix), `session_cookie_name`,
        `latest_available_app_version` (looked up on PyPI once), and `help_links` (see `_help_links`).
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
            tpls.env.globals["help_links"] = _help_links(current_version)
            cls._instance = tpls
        return cls._instance


def get_templates() -> Jinja2Templates:
    """The shared `Jinja2Templates` instance every UI route renders with."""
    return _TemplatesSingleton.load()
