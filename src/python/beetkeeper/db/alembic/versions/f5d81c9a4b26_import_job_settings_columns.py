"""import job per-job settings columns

Revision ID: f5d81c9a4b26
Revises: e2b9f4c1a307
Create Date: 2026-07-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5d81c9a4b26"
down_revision: str | None = "e2b9f4c1a307"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain (non-batch) ADD COLUMNs so this works in --sql/offline mode too (see the `quiet` revision).
    op.add_column("import_job", sa.Column("logpath", sa.String(), nullable=True))
    op.add_column("import_job", sa.Column("group_albums", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("import_job", sa.Column("flat", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("import_job", sa.Column("set_fields_json", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("import_job", schema=None) as batch_op:
        batch_op.drop_column("set_fields_json")
        batch_op.drop_column("flat")
        batch_op.drop_column("group_albums")
        batch_op.drop_column("logpath")
