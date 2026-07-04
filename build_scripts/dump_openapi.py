"""Generate `docs/openapi.json` from the beetkeeper FastAPI app for the docs site.

The REST API docs page embeds this spec via the Neoteroi OAD plugin (`[OAD(...)]`), so the docs build needs
only the mkdocs tools — not the app installed. This script DOES import the app, so run it in the app's
environment: `pants run docs:openapi` (a `run_shell_command` that shells out to `uv run`).

The output is committed. Regenerate it whenever the API surface changes; the docs CI also regenerates it
before publishing so the live site is always current.
"""

import json
from pathlib import Path

from beetkeeper.api.fastapi_app import beetkeeper_app

_OUT: Path = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def main() -> None:
    """Write the app's OpenAPI schema to `docs/openapi.json` (sorted keys for stable diffs)."""
    spec = beetkeeper_app.openapi()
    _OUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {_OUT} — {len(spec.get('paths', {}))} paths, OpenAPI {spec.get('openapi')}")


if __name__ == "__main__":
    main()
