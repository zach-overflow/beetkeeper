"""
Development-only tool exporting the beetkeeper FastAPI app's OpenAPI spec as JSON. It writes two files: the
full spec rendered in the mkdocs site via the `swagger-ui-tag` plugin, and the spec the Python API client is
generated from (`provides/client/src:openapi-spec`). Run with: `pants run etc/build_scripts:openapi-json-exporter -- <args>`.
"""

import json
from pathlib import Path
from typing import Any

import click


def _generate_current_openapi_spec() -> dict[str, Any]:
    from beetkeeper.api import create_app

    raw_app_data = create_app().openapi()
    if raw_app_data.get("info", {}).get("version"):
        raw_app_data["info"]["version"] = ""
    return raw_app_data


def _to_client_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """
    Returns the spec the API client is generated from: webhooks are requests beetkeeper sends, not endpoints a
    client calls, and openapi-generator's `python` generator crashes on their nullable parameter schemas.
    """
    return {key: value for key, value in spec.items() if key != "webhooks"}


def _serialize(spec: dict[str, Any]) -> str:
    return json.dumps(spec, indent=2) + "\n"


@click.command()
@click.pass_context
@click.option(
    "--output-filepath",
    type=click.Path(dir_okay=False, exists=False, file_okay=True, path_type=Path),
    default=Path("docs/public_api_reference/openapi.json"),
    show_default=True,
    help="File to write the docs site's `openapi.json` into, relative to the repo root when run via `pants run`.",
)
@click.option(
    "--client-output-filepath",
    type=click.Path(dir_okay=False, exists=False, file_okay=True, path_type=Path),
    default=Path("provides/client/src/openapi.json"),
    show_default=True,
    help="File to write the API client's `openapi.json` into, relative to the repo root when run via `pants run`.",
)
@click.option("--check", is_flag=True, help="When present, only check that the current JSON files are up to date.")
def main(ctx: click.Context, output_filepath: Path, client_output_filepath: Path, check: bool) -> None:
    """Exports the current beetkeeper `openapi.json` spec for the public docs site and the API client."""
    spec = _generate_current_openapi_spec()
    specs_by_filepath = {output_filepath: spec, client_output_filepath: _to_client_spec(spec)}
    if check:
        outdated = [
            str(filepath)
            for filepath, expected_spec in specs_by_filepath.items()
            if not filepath.exists()
            or json.loads(filepath.read_text(encoding="utf-8")) != json.loads(_serialize(expected_spec))
        ]
        if outdated:
            raise click.ClickException(
                f"Outdated openapi.json file(s): {', '.join(outdated)}. "
                "Run 'pants run etc/build_scripts:openapi-json-exporter' to fix."
            )
        click.echo("openapi.json files are up to date.")
        ctx.exit(0)
    for filepath, spec_to_write in specs_by_filepath.items():
        filepath.write_text(_serialize(spec_to_write), encoding="utf-8")
        click.echo(f"Wrote {filepath}")


if __name__ == "__main__":
    main()
