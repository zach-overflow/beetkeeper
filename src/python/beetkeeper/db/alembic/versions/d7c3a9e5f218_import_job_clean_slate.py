"""import job clean-slate columns, dropping the library-reimport ones

Revision ID: d7c3a9e5f218
Revises: b3f9d7c1e845
Create Date: 2026-09-24 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7c3a9e5f218"
down_revision: str | None = "b3f9d7c1e845"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain (non-batch) ALTERs so this works in --sql/offline mode too (SQLite >= 3.35 supports DROP COLUMN).
    op.add_column("import_job", sa.Column("clean_slate_album_id", sa.Integer(), nullable=True))
    op.add_column("import_job", sa.Column("clean_slate_item_id", sa.Integer(), nullable=True))
    op.add_column(
        "import_job",
        sa.Column("clean_slate_allow_fewer_files", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    for column in ("reimport_report_json", "write_tags", "move_files", "singletons", "query_json"):
        op.drop_column("import_job", column)


def downgrade() -> None:
    op.add_column("import_job", sa.Column("query_json", sa.String(), nullable=True))
    op.add_column("import_job", sa.Column("singletons", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("import_job", sa.Column("move_files", sa.Boolean(), nullable=True))
    op.add_column("import_job", sa.Column("write_tags", sa.Boolean(), nullable=True))
    op.add_column("import_job", sa.Column("reimport_report_json", sa.String(), nullable=True))
    with op.batch_alter_table("import_job", schema=None) as batch_op:
        batch_op.drop_column("clean_slate_allow_fewer_files")
        batch_op.drop_column("clean_slate_item_id")
        batch_op.drop_column("clean_slate_album_id")
