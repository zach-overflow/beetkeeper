"""
inferred source path table

Revision ID: b3f9d7c1e845
Revises: a9c4e7d2f610
Create Date: 2026-09-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3f9d7c1e845"
down_revision: str | None = "a9c4e7d2f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inferred_source_path",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("beets_id", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("query_params_json", sa.String(), nullable=True),
        sa.Column("inferred_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_type", "beets_id", name="uq_inferred_source_path_subject"),
    )


def downgrade() -> None:
    op.drop_table("inferred_source_path")
