"""switch tasks datetime columns to timestamptz

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-08 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing naive values are interpreted as UTC.
    for col in ("due_date", "created", "updated"):
        op.alter_column(
            "tasks",
            col,
            type_=postgresql.TIMESTAMP(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for col in ("due_date", "created", "updated"):
        op.alter_column(
            "tasks",
            col,
            type_=sa.DateTime(),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )
