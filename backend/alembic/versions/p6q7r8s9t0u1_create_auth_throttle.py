"""create auth_throttle

Per-account login backoff and reset-mail cooldown (#134), kept apart from
`user` on purpose: rows are keyed by an HMAC of whatever address was typed, so
unknown addresses are throttled like real ones, and the table can give way to
Redis (#245) without touching the user schema. See app/auth/throttle.py.

Nothing to backfill: every account starts with a clean slate.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-10-05 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p6q7r8s9t0u1"
down_revision: str | Sequence[str] | None = "o5p6q7r8s9t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "auth_throttle",
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        op.f("ix_auth_throttle_last_event_at"), "auth_throttle", ["last_event_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema.

    Every lock and cooldown ends; the per-address throttle stays in place.
    """
    op.drop_index(op.f("ix_auth_throttle_last_event_at"), table_name="auth_throttle")
    op.drop_table("auth_throttle")
