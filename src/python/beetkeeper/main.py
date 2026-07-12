"""Entrypoint for the beetkeeper server and FastAPI application."""

import logging
import os
from pathlib import Path

import click

from beetkeeper._cli_utils.cli_state import CliState
from beetkeeper._version import __version__ as beetkeeper_version
from beetkeeper.settings import BEETS_DIR_ENVVAR


def _inject_beetsdir_envvar_callback(ctx: click.Context, param: click.Parameter, value: Path) -> Path:
    """
    Click callback for setting the `BEETS_DIR_ENVVAR` value if it is not already set (i.e. if the user passed
    `--beetsdir` rather than calling the app with the envvar set). This is to inject the beets config path into
    the server app since `uvicorn.run` doesn't allow passing arbitrary custom commands to the target ASGI.
    """
    resolved_path = value.expanduser().resolve()
    # Export the config's directory as BEETSDIR so the app's lifespan (a fresh import under uvicorn
    # reload/workers) resolves the same `<BEETSDIR>/config.yaml` to initialize its DB engine. Assumes the
    # config file is named `config.yaml` (beets' convention). See `beetkeeper.api.fastapi_app.lifespan`.
    if not os.getenv(BEETS_DIR_ENVVAR):
        os.environ[BEETS_DIR_ENVVAR] = str(resolved_path)
    return resolved_path


@click.version_option(beetkeeper_version, message="%(version)s")
@click.group()
@click.option(
    "-b",
    "--beetsdir",
    "beetsdir_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    callback=_inject_beetsdir_envvar_callback,
    envvar=BEETS_DIR_ENVVAR,
    required=True,
    help="Path to the beets directory containing the beets config file and library database.",
)
@click.pass_context
def cli(ctx: click.Context, beetsdir_path: Path) -> None:
    # https://click.palletsprojects.com/en/stable/complex/#the-root-command
    ctx.obj = CliState(beetsdir_path=beetsdir_path)


@cli.command(help="Run the webserver with the given configuration.")
@click.pass_obj
def run(cli_state: CliState) -> None:
    # Function-scoped import for quicker top-level CLI loading.
    import uvicorn

    from beetkeeper.db.migrations import MigrationStateError, alembic_config_from_user_config, startup_upgrade

    user_config = cli_state.user_config
    # Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
    logging.basicConfig(level=user_config.log_level, handlers=[logging.StreamHandler()])
    # Migrate before uvicorn forks its workers: a single process runs the upgrade, so `server_workers > 1`
    # can't race on it, and every worker's lifespan sees a current schema.
    try:
        startup_upgrade(
            alembic_config_from_user_config(user_config),
            sqlite_path=user_config.database.resolved_sqlite_path,
            auto_upgrade=user_config.database.auto_upgrade,
        )
    except MigrationStateError as e:
        raise click.ClickException(str(e)) from e
    # Production/container run: multi-worker, no autoreload (reload is incompatible with workers>1, and
    # `--reload` is a dev-only concern). uvicorn wants a lowercase log level string.
    uvicorn.run(
        app="beetkeeper.api:create_app",
        factory=True,
        host=user_config.server.hostname,
        port=user_config.server.port,
        log_level=user_config.log_level.lower(),
        workers=user_config.server.server_workers,
    )


@cli.group(help="Database migration commands (alembic).")
def db() -> None:
    pass


@db.command(name="upgrade", help="Apply migrations up to a revision (default: head).")
@click.option("--revision", default="head", show_default=True, help="Target revision to upgrade to.")
@click.option(
    "--sql", "as_sql", is_flag=True, default=False, help="Offline mode: print SQL to stdout instead of applying it."
)
@click.pass_obj
def db_upgrade(cli_state: CliState, revision: str, as_sql: bool) -> None:
    # Function-scoped import keeps alembic/sqlalchemy off the hot path for non-db CLI invocations.
    from beetkeeper.db.migrations import upgrade

    upgrade(cli_state.alembic_config, revision, sql=as_sql)


@db.command(name="downgrade", help="Revert migrations down to a revision (e.g. 'base').")
@click.option("--revision", required=True, help="Target revision to downgrade to (e.g. 'base' or a revision id).")
@click.option(
    "--sql", "as_sql", is_flag=True, default=False, help="Offline mode: print SQL to stdout instead of applying it."
)
@click.pass_obj
def db_downgrade(cli_state: CliState, revision: str, as_sql: bool) -> None:
    from beetkeeper.db.migrations import downgrade

    downgrade(cli_state.alembic_config, revision, sql=as_sql)


if __name__ == "__main__":
    cli(prog_name="beetkeeper")
