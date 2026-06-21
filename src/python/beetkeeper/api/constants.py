from pathlib import Path
from typing import Final

from starlette.templating import Jinja2Templates

STATIC_DIRPATH: Final[Path] = Path(__file__).resolve().parent / "static"
TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(directory=STATIC_DIRPATH / "html_templates")
