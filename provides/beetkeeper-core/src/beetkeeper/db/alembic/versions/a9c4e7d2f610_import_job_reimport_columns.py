"""
import job reimport columns

Revision ID: a9c4e7d2f610
Revises: e1b7d5c2a984
Create Date: 2026-09-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e7d2f610"
down_revision: str | None = "e1b7d5c2a984"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain (non-batch) ADD COLUMNs so this works in --sql/offline mode too (see the `quiet` revision).
    op.add_column("import_job", sa.Column("query_json", sa.String(), nullable=True))
    op.add_column("import_job", sa.Column("singletons", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("import_job", sa.Column("move_files", sa.Boolean(), nullable=True))
    op.add_column("import_job", sa.Column("write_tags", sa.Boolean(), nullable=True))
    op.add_column("import_job", sa.Column("reimport_report_json", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("import_job", schema=None) as batch_op:
        batch_op.drop_column("reimport_report_json")
        batch_op.drop_column("write_tags")
        batch_op.drop_column("move_files")
        batch_op.drop_column("singletons")
        batch_op.drop_column("query_json")
