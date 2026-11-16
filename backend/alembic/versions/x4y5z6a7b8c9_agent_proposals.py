"""agent proposals

The staging queue for changes an agent wants made (#321): a create, update or
archive waits here until the operator approves or rejects it. See
app/models/proposal.py.

Nothing to backfill. Expand only: the previous release ignores the table.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-11-16 20:17:18.455062

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "x4y5z6a7b8c9"
down_revision: str | Sequence[str] | None = "w3x4y5z6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("api_token_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("proposed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applied_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["api_token_id"], ["api_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_proposals_user_status",
        "agent_proposals",
        ["user_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema.

    Every pending proposal is lost; agents resubmit what they still want.
    """
    op.drop_index("ix_agent_proposals_user_status", table_name="agent_proposals")
    op.drop_table("agent_proposals")
