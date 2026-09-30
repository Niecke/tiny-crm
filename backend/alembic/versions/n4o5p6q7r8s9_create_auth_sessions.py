"""create auth_sessions

One row per signed-in device (#133), so a login can be ended server-side: on
sign-out, on a password change, on a password reset. Access tokens name their
row in a `sid` claim and stop working when it is deleted; refresh tokens are
checked against `generation`. No token or token hash is stored — see
app/auth/sessions.py.

Nothing to backfill, and that is a breaking change on purpose: the 270-day
tokens issued before this carry no `sid` and are refused, so every client signs
in once more after the deploy. Keeping them valid would keep exactly the
unrevocable tokens this table exists to end.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-09-30 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n4o5p6q7r8s9"
down_revision: str | Sequence[str] | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Every session ends. The code this downgrades to issues its own
    session-less tokens, so everyone simply signs in again.
    """
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
