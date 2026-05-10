"""add tags to tasks

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "tags")
