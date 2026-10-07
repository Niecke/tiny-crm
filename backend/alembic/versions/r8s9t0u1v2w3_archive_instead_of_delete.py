"""archived_at on every record table

Archive instead of delete (#140): one nullable timestamp per table, NULL for
everything still in use. See app/archive.py for what an archived row is.

Nothing to backfill — nothing has been archived yet — and no index: every list
is already narrowed to one operator's rows by `user_id`, and "not archived" is
nearly all of them. #139 measures which filter columns earn an index.

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-10-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r8s9t0u1v2w3"
down_revision: str | Sequence[str] | None = "q7r8s9t0u1v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "contacts",
    "organizations",
    "deals",
    "tasks",
    "interactions",
    "projects",
    "documents",
    "watches",
    "captures",
)


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema.

    Archived rows come back as ordinary ones: without the column nothing can
    tell them apart, and dropping them instead would turn a downgrade into the
    delete this was built to avoid.
    """
    for table in TABLES:
        op.drop_column(table, "archived_at")
