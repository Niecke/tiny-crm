"""two-factor sign-in

TOTP with an authenticator app (#18): the sealed secret and its state on
`user`, single-use recovery codes in their own table. See app/auth/mfa.py.

Nothing to backfill: every account starts with MFA off. Expand only: the
previous release ignores the columns and the table, and while both run it
signs in accounts that have MFA on with the password alone.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-10-08 20:35:47.934466

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "u1v2w3x4y5z6"
down_revision: str | Sequence[str] | None = "t0u1v2w3x4y5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("user", sa.Column("mfa_secret", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mfa_recovery_codes_user_id"), "mfa_recovery_codes", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema.

    Every account is back to password-only sign-in; the secrets and recovery
    codes are gone, so MFA has to be set up again after a re-upgrade.
    """
    op.drop_index(op.f("ix_mfa_recovery_codes_user_id"), table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_column("user", "mfa_last_step")
    op.drop_column("user", "mfa_enabled_at")
    op.drop_column("user", "mfa_secret")
