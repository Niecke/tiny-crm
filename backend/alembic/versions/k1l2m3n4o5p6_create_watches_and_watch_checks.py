"""create watches and watch checks

The intake end of the pipeline: the job boards, careers pages and tender portals
that get swept on a cadence, plus the append-only log of every sweep.

Two tables rather than three columns on `organizations`, because the sources
that matter most are not companies — a job board with a saved search and a
tender portal are things you check, not parties you have a relationship with.
A careers page is the special case where `organization_id` is set.

Nothing to backfill; there was nowhere a watch could previously have lived.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-09-02 10:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k1l2m3n4o5p6"
down_revision: str | Sequence[str] | None = "j0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "watches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        # Plain text, constrained to the known kinds by the Pydantic schema —
        # a native enum would make adding a kind an ALTER TYPE migration.
        sa.Column("kind", sa.String(), server_default="other", nullable=False),
        sa.Column("query_note", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        # The cadence, same rule set as tasks.recurrence_rule.
        sa.Column("recurrence_rule", sa.String(), nullable=False),
        sa.Column("recurrence_interval", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        # Not null: every watch is due at some point, and the sweep list sorts
        # on it. A brand new watch is due immediately.
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # SET NULL: losing the company must not delete the source you watch it
        # through — the careers page is still worth checking.
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_watches_user_id"), "watches", ["user_id"], unique=False)
    op.create_index(op.f("ix_watches_kind"), "watches", ["kind"], unique=False)
    op.create_index(
        op.f("ix_watches_organization_id"), "watches", ["organization_id"], unique=False
    )
    # The column every sweep query sorts and filters on.
    op.create_index(op.f("ix_watches_next_due_at"), "watches", ["next_due_at"], unique=False)

    op.create_table(
        "watch_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("watch_id", sa.Uuid(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(), server_default="nothing", nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_deal_id", sa.Uuid(), nullable=True),
        sa.Column("created_task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # CASCADE from the watch — the log is part of it. SET NULL on what a
        # find produced: deleting the deal must not erase the record of having
        # found it.
        sa.ForeignKeyConstraint(["watch_id"], ["watches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_deal_id"], ["deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_watch_checks_user_id"), "watch_checks", ["user_id"], unique=False)
    op.create_index(op.f("ix_watch_checks_watch_id"), "watch_checks", ["watch_id"], unique=False)
    op.create_index(
        op.f("ix_watch_checks_checked_at"), "watch_checks", ["checked_at"], unique=False
    )
    op.create_index(
        op.f("ix_watch_checks_created_deal_id"), "watch_checks", ["created_deal_id"], unique=False
    )
    op.create_index(
        op.f("ix_watch_checks_created_task_id"), "watch_checks", ["created_task_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_watch_checks_created_task_id"), table_name="watch_checks")
    op.drop_index(op.f("ix_watch_checks_created_deal_id"), table_name="watch_checks")
    op.drop_index(op.f("ix_watch_checks_checked_at"), table_name="watch_checks")
    op.drop_index(op.f("ix_watch_checks_watch_id"), table_name="watch_checks")
    op.drop_index(op.f("ix_watch_checks_user_id"), table_name="watch_checks")
    op.drop_table("watch_checks")

    op.drop_index(op.f("ix_watches_next_due_at"), table_name="watches")
    op.drop_index(op.f("ix_watches_organization_id"), table_name="watches")
    op.drop_index(op.f("ix_watches_kind"), table_name="watches")
    op.drop_index(op.f("ix_watches_user_id"), table_name="watches")
    op.drop_table("watches")
