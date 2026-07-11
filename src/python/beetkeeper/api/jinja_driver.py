import json
import logging
from functools import cache
from typing import ClassVar

from starlette.templating import Jinja2Templates

from beetkeeper._version import __version__
from beetkeeper.api.constants import STATIC_DIRPATH

_LOGGER = logging.getLogger(__name__)


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
        _LOGGER.error(f"Failed to pulling version info from {pypi_url}. Got http error code {e.response.status_code}.")
    except KeyError:
        pretty_json = json.dumps(pypi_pkg_response_json, indent=2)
        _LOGGER.error(f"Failed to get version info from PyPI version response JSON from {pypi_url}:\n{pretty_json}")
    except Exception as e:
        _LOGGER.error(f"Unexpected failure during version lookup attempt: {str(e)}")
    return latest_available_app_version


# TODO[Claude]: two things to resolve here:
#   1. HTMX fragment rendering: this is a plain Starlette `Jinja2Templates`, but `jinja2-fragments` is a
#      declared dependency. If routes need to return a single template block for an HTMX swap, switch to
#      `jinja2_fragments.fastapi.Jinja2Blocks` (and standardize block usage). Decide and document.
#   2. Templates live inside the publicly mounted `static/` tree, so raw `.html` template source is also reachable at
#      `/static/html_templates/...`. If that exposure is unintended, relocate templates out of `static/`.
class _TemplatesSingleton:
    _instance: ClassVar[Jinja2Templates | None] = None

    @classmethod
    def load(cls) -> Jinja2Templates:
        if not cls._instance:
            tpls = Jinja2Templates(directory=STATIC_DIRPATH / "html_templates")
            current_version = __version__
            if "+" in current_version:
                current_version = current_version.split("+")[0]
            tpls.env.globals["current_app_version"] = current_version
            tpls.env.globals["latest_available_app_version"] = _get_latest_available_version_semver()
            cls._instance = tpls
        return cls._instance


def get_templates() -> Jinja2Templates:
    return _TemplatesSingleton.load()
