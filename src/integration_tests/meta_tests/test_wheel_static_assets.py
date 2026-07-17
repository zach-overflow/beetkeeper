"""Guard that the webserver's static assets ship in the `beetkeeper` wheel.

The wheel is built with `generate_setup=False` (see `src/python/BUILD`), so *setuptools* — not Pants —
decides which non-`.py` files land in the wheel, driven entirely by `[tool.setuptools.package-data]` in
`src/python/pyproject.toml`. The static assets under `beetkeeper/api/static/**` live in non-package subdirs
(no `__init__.py`), so a non-recursive glob like `"*.css"` (relative to the top `beetkeeper/` package dir)
never matches them and they silently drop out of the wheel — a runtime break (404/500 on CSS, templates,
HTMX, favicons) that a plain `import` test can't catch.

This asserts every on-disk static file is matched by at least one `package-data` glob, so the wheel actually
ships them. `PurePosixPath.full_match` (3.13+) applies the same `**`-recursive glob semantics setuptools uses.
"""

from pathlib import Path, PurePosixPath
from typing import Final, TYPE_CHECKING


if TYPE_CHECKING:
    import tomlkit


# package-data globs are relative to the top-level package directory (`beetkeeper/`).
_PACKAGE_RELPATH: Final[str] = "src/python/beetkeeper"
_STATIC_RELPATH: Final[str] = "src/python/beetkeeper/api/static"


def test_all_static_assets_are_covered_by_package_data(
    repo_root: Path, bk_pyproject_data: tomlkit.TOMLDocument
) -> None:
    """Every file under `beetkeeper/api/static/` must match a `package-data` glob, or it won't ship."""
    package_dir = repo_root / _PACKAGE_RELPATH
    globs = bk_pyproject_data["tool"]["setuptools"]["package-data"]["beetkeeper"]
    static_files = sorted(
        [
            p
            for p in (repo_root / _STATIC_RELPATH).rglob("*")
            if p.is_file() and p.name != "BUILD" and "__pycache__" not in p.parts
        ]
    )
    assert static_files, f"Found no static assets under `{_STATIC_RELPATH}` — the test cannot validate anything."

    uncovered = [
        str(rel)
        for f in static_files
        if not any((rel := PurePosixPath(f.relative_to(package_dir).as_posix())).full_match(g) for g in globs)
    ]
    assert not uncovered, (
        "These static assets match no `[tool.setuptools.package-data].beetkeeper` glob, so they will NOT ship "
        f"in the wheel (built with generate_setup=False): {uncovered}. Add a recursive, path-qualified pattern "
        "(e.g. `api/static/**/*.<ext>`) to `src/python/pyproject.toml`."
    )
