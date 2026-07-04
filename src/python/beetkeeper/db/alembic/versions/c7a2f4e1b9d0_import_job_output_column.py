"""import job output column

Revision ID: c7a2f4e1b9d0
Revises: bcdd3073515d
Create Date: 2026-06-27 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a2f4e1b9d0"
down_revision: str | None = "bcdd3073515d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("import_job", schema=None) as batch_op:
        batch_op.add_column(sa.Column("output", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("import_job", schema=None) as batch_op:
        batch_op.drop_column("output")
