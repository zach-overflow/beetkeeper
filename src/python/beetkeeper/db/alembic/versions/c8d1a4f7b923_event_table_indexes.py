"""event table indexes

Revision ID: c8d1a4f7b923
Revises: b6e0f3a9c512
Create Date: 2026-08-08 12:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8d1a4f7b923"
down_revision: str | None = "b6e0f3a9c512"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_listener_event_pushed_at_event_id", "listener_event", ["pushed_at", "event_id"], unique=False)
    op.create_index("ix_album_event_listener_event_id", "album_event", ["listener_event_id"], unique=False)
    op.create_index("ix_album_event_beets_album_id", "album_event", ["beets_album_id"], unique=False)
    op.create_index("ix_track_event_listener_event_id", "track_event", ["listener_event_id"], unique=False)
    op.create_index("ix_track_event_beets_item_id", "track_event", ["beets_item_id"], unique=False)
    op.create_index(
        "ix_import_source_path_listener_event_id", "import_source_path", ["listener_event_id"], unique=False
    )
    op.create_index(
        "ix_import_destination_path_listener_event_id", "import_destination_path", ["listener_event_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_import_destination_path_listener_event_id", table_name="import_destination_path")
    op.drop_index("ix_import_source_path_listener_event_id", table_name="import_source_path")
    op.drop_index("ix_track_event_beets_item_id", table_name="track_event")
    op.drop_index("ix_track_event_listener_event_id", table_name="track_event")
    op.drop_index("ix_album_event_beets_album_id", table_name="album_event")
    op.drop_index("ix_album_event_listener_event_id", table_name="album_event")
    op.drop_index("ix_listener_event_pushed_at_event_id", table_name="listener_event")
