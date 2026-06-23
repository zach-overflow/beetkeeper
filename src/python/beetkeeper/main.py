"""Entrypoint for the beetkeeper server and FastAPI application."""

import logging
from pathlib import Path

import click

from beetkeeper._version import __version__ as beetkeeper_version
from beetkeeper.settings import CONFIG_PATH_ENVVAR, load_config


@click.version_option(beetkeeper_version, message="%(version)s")
@click.group()
def cli() -> None:
    pass


@cli.command(help="Run the webserver with the given configuration.")
# TODO[Claude]: the `--config-path` help text is wrong (copy-paste: "Sets the server log level."). Also,
#     `config_path` is neither `required=True` nor defaulted, so if both the flag and `BEETKEEPER_CONFIG`
#     are absent it arrives as `None`, and `load_config(None)` -> `Path(None)` raises `TypeError` instead of
#     the intended `BeetKeeperConfigError`. Make it required (or default + friendly error).
@click.option(
    "-c",
    "--config-path",
    envvar=[CONFIG_PATH_ENVVAR],
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Sets the server log level.",
)
def run(config_path: Path) -> None:
    # Function-scoped import for quicker top-level CLI loading.
    import uvicorn

    user_config = load_config(raw_conf_path=config_path)
    # Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
    logging.basicConfig(level=user_config.log_level, handlers=[logging.StreamHandler()])
    # TODO[Claude]: several uvicorn issues to resolve before this runs as intended:
    #   - `reload=True` is incompatible with `workers>1` (default `server_workers=2`); uvicorn ignores
    #     workers and/or errors. Decide dev (reload, 1 worker) vs. prod (workers, no reload), likely via
    #     `UserConfig`, instead of hardcoding `reload=True`.
    #   - `reload_dirs` are CWD-relative (fragile) and `./api/templates` does not exist (templates live
    #     under `api/static/html_templates`). Use absolute paths derived from the package.
    uvicorn.run(
        app="beetkeeper.api:beetkeeper",
        host=user_config.hostname,
        port=user_config.port,
        reload=True,
        reload_dirs=["./api/static", "./api/templates"],
        reload_includes=["*.css", "*.js", "*.html", "*.template"],
        log_level=user_config.log_level,
        workers=user_config.server_workers,
    )


if __name__ == "__main__":
    cli(prog_name="beetkeeper")
