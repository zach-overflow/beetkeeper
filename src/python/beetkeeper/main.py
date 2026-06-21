"""Entrypoint for the beetkeeper server and FastAPI application."""

import logging
from pathlib import Path

import click

from beetkeeper._version import __version__ as app_version
from beetkeeper.settings import CONFIG_PATH_ENVVAR, load_config


@click.version_option(app_version, message="%(version)s")
@click.group()
def cli() -> None:
    pass


@cli.command(help="Run the webserver with the given configuration.")
@click.option(
    "-c",
    "--config-path",
    envvar=[CONFIG_PATH_ENVVAR],
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Sets the server log level.",
)
def run(config_path: Path) -> None:
    import uvicorn

    from beetkeeper.api import beetkeeper_app

    user_config = load_config(raw_conf_path=config_path)
    # Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
    logging.basicConfig(level=user_config.log_level, handlers=[logging.StreamHandler()])
    uvicorn.run(
        app=beetkeeper_app,
        host=user_config.hostname,
        port=user_config.port,
        reload=True,
        reload_dirs=["./api/static", "./api/templates"],
        reload_includes=["*.css", "*.js", "*.html", "*.html.tpl", "*.template"],
        log_level=user_config.log_level,
        workers=user_config.server_workers,
    )


if __name__ == "__main__":
    cli(prog_name="beetkeeper")
