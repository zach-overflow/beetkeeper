"""event subject name columns

Revision ID: e1b7d5c2a984
Revises: c8d1a4f7b923
Create Date: 2026-08-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1b7d5c2a984"
down_revision: str | None = "c8d1a4f7b923"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("album_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("album_name", sa.String(), nullable=True))
    with op.batch_alter_table("track_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("track_title", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("album_name", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("track_event", schema=None) as batch_op:
        batch_op.drop_column("album_name")
        batch_op.drop_column("track_title")
    with op.batch_alter_table("album_event", schema=None) as batch_op:
        batch_op.drop_column("album_name")
