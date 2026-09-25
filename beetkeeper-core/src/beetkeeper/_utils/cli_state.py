from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from beetkeeper.settings import BEETS_CONFIG_FILENAME, UserConfig, load_config

if TYPE_CHECKING:
    from alembic.config import Config


@dataclass(frozen=True)
class CliState:
    """
    Immutable wrapper for common CLI state / click context sharing across commands.
    See also:
        https://click.palletsprojects.com/en/stable/commands/#nested-handling-and-contexts
    """

    beetsdir_path: Path

    @property
    def user_config(self) -> UserConfig:
        """Returns the `beetkeeper.settings.UserConfig` instance from the provided beets `config.yaml`."""
        return load_config(raw_conf_path=self.beetsdir_path / BEETS_CONFIG_FILENAME)

    @property
    def alembic_config(self) -> Config:
        """
        Returns the application's alembic configuration. Only relevant for version upgrades / downgrades requiring
        beetkeeper DB schema changes.
        """
        from beetkeeper.db.migrations import alembic_config_from_user_config

        return alembic_config_from_user_config(self.user_config)
