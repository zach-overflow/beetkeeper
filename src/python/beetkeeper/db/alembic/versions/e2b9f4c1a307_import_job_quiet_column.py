"""import job quiet column

Revision ID: e2b9f4c1a307
Revises: c7a2f4e1b9d0
Create Date: 2026-06-27 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2b9f4c1a307"
down_revision: str | None = "c7a2f4e1b9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain (non-batch) ADD COLUMN: SQLite adds a column in place, so this works in --sql/offline mode too
    # (batch mode would need a live DB to reflect the table). NOT NULL needs a default for existing rows,
    # hence `server_default`; the model has no server_default and env.py doesn't compare them, so it's
    # diff-free against the models.
    op.add_column("import_job", sa.Column("quiet", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    with op.batch_alter_table("import_job", schema=None) as batch_op:
        batch_op.drop_column("quiet")
