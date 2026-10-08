"""completed_at on tasks

`done` says whether a task is finished, not when, so "tasks completed this
month" could not be counted (#138).

Tasks already done get `updated` as their completion time. That is an
estimate — the last write to the row, which for a finished task is nearly
always the tick that finished it — and it is the only record there is. Left
NULL, everything completed before this migration would be missing from every
period, and the dashboard would report a quarter in which nothing got done.

Expand only: the previous release ignores the column. A task it completes
while both are running gets no timestamp and is not counted.

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-10-08 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t0u1v2w3x4y5"
down_revision: str | Sequence[str] | None = "s9t0u1v2w3x4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tasks SET completed_at = updated WHERE done")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tasks", "completed_at")
