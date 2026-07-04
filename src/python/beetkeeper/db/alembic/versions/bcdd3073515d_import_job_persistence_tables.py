"""import job persistence tables

Revision ID: bcdd3073515d
Revises: 7f3051110f7f
Create Date: 2026-06-26 17:58:17.397558

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bcdd3073515d"
down_revision: str | None = "7f3051110f7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_job",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("paths_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("abort_requested", sa.Boolean(), nullable=False),
        sa.Column("pending_decision_json", sa.String(), nullable=True),
        sa.Column("submitted_decision_json", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "import_lock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("holder", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("import_lock")
    op.drop_table("import_job")
