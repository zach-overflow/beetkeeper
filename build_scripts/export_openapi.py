"""
Development-only tool exporting the beetkeeper FastAPI app's OpenAPI spec as JSON, for rendering in the
mkdocs site via the `swagger-ui-tag` plugin. Run with: `pants run build_scripts:openapi-json-exporter -- <args>`.
"""

import json
from pathlib import Path

import click


def _generate_current_openapi_json() -> str:
    from beetkeeper.api import create_app

    raw_app_data = create_app().openapi()
    if raw_app_data.get("info", {}).get("version"):
        raw_app_data["info"]["version"] = ""
    return json.dumps(raw_app_data, indent=2) + "\n"


@click.command()
@click.pass_context
@click.option(
    "--output-filepath",
    type=click.Path(dir_okay=False, exists=False, file_okay=True, path_type=Path),
    default=Path("docs/public_api_reference/openapi.json"),
    show_default=True,
    help="Directory to write `openapi.json` into, relative to the repo root when run via `pants run`.",
)
@click.option("--check", is_flag=True, help="When present, only check that the current JSON file is up to date.")
def main(ctx: click.Context, output_filepath: Path, check: bool) -> None:
    """Exports the current beetkeeper `openapi.json` spec for the public docs site."""
    if check:
        spec_from_file = json.loads(output_filepath.read_text(encoding="utf-8"))
        spec_from_app = json.loads(_generate_current_openapi_json())
        if spec_from_file != spec_from_app:
            raise click.ClickException(
                "Current openapi.json file contents are outdated. Run 'pants run build_scripts:openapi-json-exporter' to fix."
            )
        click.echo("openapi.json is up to date.")
        ctx.exit(0)
    output_filepath.write_text(_generate_current_openapi_json(), encoding="utf-8")
    click.echo(f"Wrote {output_filepath}")


if __name__ == "__main__":
    main()
