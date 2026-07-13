"""auth session table

Revision ID: d4e8a2c6b1f3
Revises: f5d81c9a4b26
Create Date: 2026-07-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8a2c6b1f3"
down_revision: str | None = "f5d81c9a4b26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_session",
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("auth_session")
