"""link tasks to contacts, deals and interactions

Tasks attached only to projects, so "call Maria back on Thursday" had nowhere
to record who Maria is. Three independent nullable FKs, all SET NULL: deleting
the person, the deal or the call must not silently drop work the operator
committed to.

Nothing to backfill — there was no earlier column holding any of these.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-08-31 21:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i9j0k1l2m3n4"
down_revision: str | Sequence[str] | None = "h8i9j0k1l2m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (column, referenced table, index name, constraint name)
LINKS = (
    ("contact_id", "contacts"),
    ("deal_id", "deals"),
    ("interaction_id", "interactions"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for column, table in LINKS:
        op.add_column("tasks", sa.Column(column, sa.Uuid(), nullable=True))
        op.create_index(op.f(f"ix_tasks_{column}"), "tasks", [column], unique=False)
        op.create_foreign_key(
            f"fk_tasks_{column}_{table}",
            "tasks",
            table,
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    for column, table in reversed(LINKS):
        op.drop_constraint(f"fk_tasks_{column}_{table}", "tasks", type_="foreignkey")
        op.drop_index(op.f(f"ix_tasks_{column}"), table_name="tasks")
        op.drop_column("tasks", column)
