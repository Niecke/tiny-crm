"""deal stage timestamps and stage-change events

Nothing recorded when a deal last moved, so "how long has this been in
proposal?" had no answer and no velocity metric could be computed.

`deals.stage_changed_at` is backfilled from `created_at`. That is wrong for any
deal that has already moved, but it is the only honest floor available: a deal
cannot have entered its current stage before it existed, so every age computed
from it is an underestimate, never an overestimate.

`deal_stage_events` starts empty. There is no history to reconstruct, and
inventing one creation event per existing deal would put fake rows into every
"entered this period" count.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-10-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o5p6q7r8s9t0"
down_revision: str | Sequence[str] | None = "n4o5p6q7r8s9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable first, backfilled, then tightened — NOT NULL with no default
    # cannot be added to a table that already has rows.
    op.add_column("deals", sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE deals SET stage_changed_at = created_at")
    op.alter_column("deals", "stage_changed_at", nullable=False)
    op.create_index(op.f("ix_deals_stage_changed_at"), "deals", ["stage_changed_at"], unique=False)

    op.create_table(
        "deal_stage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        # NULL only on the event that records a deal being created.
        sa.Column("from_stage", sa.String(), nullable=True),
        sa.Column("to_stage", sa.String(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lost_reason", sa.String(), nullable=True),
        # CASCADE: the history is part of the deal.
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deal_stage_events_deal_id"), "deal_stage_events", ["deal_id"], unique=False
    )
    op.create_index(
        op.f("ix_deal_stage_events_changed_at"), "deal_stage_events", ["changed_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_deal_stage_events_changed_at"), table_name="deal_stage_events")
    op.drop_index(op.f("ix_deal_stage_events_deal_id"), table_name="deal_stage_events")
    op.drop_table("deal_stage_events")

    op.drop_index(op.f("ix_deals_stage_changed_at"), table_name="deals")
    op.drop_column("deals", "stage_changed_at")
