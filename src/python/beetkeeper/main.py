"""Entrypoint for the beetkeeper server and FastAPI application."""

import logging
import os
from pathlib import Path

import click

from beetkeeper._version import __version__ as beetkeeper_version
from beetkeeper.settings import CONFIG_PATH_ENVVAR, load_config

# Reusable config-path option shared by the server and db subcommands (sources the flag or BEETKEEPER_CONFIG).
# Points at the BEETS config; beetkeeper reads its own settings from that file's optional `beetkeeper` section.
config_path_option = click.option(
    "-c",
    "--config-path",
    envvar=[CONFIG_PATH_ENVVAR],
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Path to the beets YAML config; beetkeeper reads its settings from that file's optional "
        f"`beetkeeper` section (or set the {CONFIG_PATH_ENVVAR} env var)."
    ),
)


@click.version_option(beetkeeper_version, message="%(version)s")
@click.group()
def cli() -> None:
    pass


@cli.command(help="Run the webserver with the given configuration.")
@config_path_option
def run(config_path: Path) -> None:
    # Function-scoped import for quicker top-level CLI loading.
    import uvicorn

    user_config = load_config(raw_conf_path=config_path)
    # Export the resolved config path so the app's lifespan (a fresh import under uvicorn reload/workers)
    # can load the same config to initialize its DB engine. See `beetkeeper.api.fastapi_app.lifespan`.
    os.environ[CONFIG_PATH_ENVVAR] = str(config_path)
    # Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
    logging.basicConfig(level=user_config.log_level, handlers=[logging.StreamHandler()])
    # Production/container run: multi-worker, no autoreload (reload is incompatible with workers>1, and
    # `--reload` is a dev-only concern). uvicorn wants a lowercase log level string.
    uvicorn.run(
        app="beetkeeper.api:beetkeeper_app",
        host=user_config.server.hostname,
        port=user_config.server.port,
        log_level=user_config.log_level.lower(),
        workers=user_config.server.server_workers,
    )


@cli.group(help="Database migration commands (alembic).")
def db() -> None:
    pass


@db.command(name="upgrade", help="Apply migrations up to a revision (default: head).")
@config_path_option
@click.option("--revision", default="head", show_default=True, help="Target revision to upgrade to.")
@click.option(
    "--sql", "as_sql", is_flag=True, default=False, help="Offline mode: print SQL to stdout instead of applying it."
)
def db_upgrade(config_path: Path, revision: str, as_sql: bool) -> None:
    # Function-scoped import keeps alembic/sqlalchemy off the hot path for non-db CLI invocations.
    from beetkeeper.db.migrations import config_from_user_config, upgrade

    upgrade(config_from_user_config(load_config(raw_conf_path=config_path)), revision, sql=as_sql)


@db.command(name="downgrade", help="Revert migrations down to a revision (e.g. 'base').")
@config_path_option
@click.option("--revision", required=True, help="Target revision to downgrade to (e.g. 'base' or a revision id).")
@click.option(
    "--sql", "as_sql", is_flag=True, default=False, help="Offline mode: print SQL to stdout instead of applying it."
)
def db_downgrade(config_path: Path, revision: str, as_sql: bool) -> None:
    from beetkeeper.db.migrations import config_from_user_config, downgrade

    downgrade(config_from_user_config(load_config(raw_conf_path=config_path)), revision, sql=as_sql)


if __name__ == "__main__":
    cli(prog_name="beetkeeper")
