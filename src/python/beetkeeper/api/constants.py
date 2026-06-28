from pathlib import Path
from typing import Final

from starlette.templating import Jinja2Templates

STATIC_DIRPATH: Final[Path] = Path(__file__).resolve().parent / "static"
# TODO[Claude]: two things to resolve here:
#   1. HTMX fragment rendering: this is a plain Starlette `Jinja2Templates`, but `jinja2-fragments` is a
#      declared dependency. If routes need to return a single template block for an HTMX swap, switch to
#      `jinja2_fragments.fastapi.Jinja2Blocks` (and standardize block usage). Decide and document.
#   2. Templates live inside the publicly mounted `static/` tree, so raw `.html` template source is also reachable at
#      `/static/html_templates/...`. If that exposure is unintended, relocate templates out of `static/`.
TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(directory=STATIC_DIRPATH / "html_templates")
