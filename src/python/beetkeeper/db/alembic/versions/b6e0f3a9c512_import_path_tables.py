"""import path tables

Revision ID: b6e0f3a9c512
Revises: d4e8a2c6b1f3
Create Date: 2026-08-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e0f3a9c512"
down_revision: str | None = "d4e8a2c6b1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_source_path",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listener_event_id", sa.Integer(), nullable=True),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["listener_event_id"], ["listener_event.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "import_destination_path",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listener_event_id", sa.Integer(), nullable=True),
        sa.Column("destination_path", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["listener_event_id"], ["listener_event.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("import_destination_path")
    op.drop_table("import_source_path")
