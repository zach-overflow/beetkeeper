"""initial event tables

Revision ID: 7f3051110f7f
Revises:
Create Date: 2026-06-23 13:39:43.549417

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f3051110f7f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listener_event",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("pushed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "album_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listener_event_id", sa.Integer(), nullable=True),
        sa.Column("beets_album_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["listener_event_id"], ["listener_event.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "track_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listener_event_id", sa.Integer(), nullable=True),
        sa.Column("beets_item_id", sa.Integer(), nullable=False),
        sa.Column("beets_album_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["listener_event_id"], ["listener_event.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("track_event")
    op.drop_table("album_event")
    op.drop_table("listener_event")
