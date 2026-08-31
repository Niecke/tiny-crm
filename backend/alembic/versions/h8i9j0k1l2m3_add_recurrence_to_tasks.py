"""add recurrence to tasks

Revision ID: h8i9j0k1l2m3
Revises: 4b7e2d91c6fa
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: str | Sequence[str] | None = "4b7e2d91c6fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("recurrence_rule", sa.String(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("recurrence_interval", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("recurrence_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("recurrence_parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # SET NULL: deleting one completed instance must not delete the series.
    op.create_foreign_key(
        "fk_tasks_recurrence_parent_id_tasks",
        "tasks",
        "tasks",
        ["recurrence_parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_recurrence_parent_id", "tasks", ["recurrence_parent_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_recurrence_parent_id", table_name="tasks")
    op.drop_constraint("fk_tasks_recurrence_parent_id_tasks", "tasks", type_="foreignkey")
    op.drop_column("tasks", "recurrence_parent_id")
    op.drop_column("tasks", "recurrence_until")
    op.drop_column("tasks", "recurrence_interval")
    op.drop_column("tasks", "recurrence_rule")
