"""create captures

The inbox: a name or a link, parked in seconds, to be worked later.

A table of its own rather than more nullable columns on `contacts`. A contact
needs a name and rewards a dozen more fields, so a bare profile URL could not
be filed as one without inventing a name for it — and a contact list that is
mostly stubs stops being trustworthy. Worse, the filters that make that list
useful (`lifecycle_status`, `works_with_freelancers`) read as "never asked" on
a stub, which is indistinguishable from a real answer.

`contact_id` and `deal_id` record what a capture turned into, both SET NULL:
deleting the person must not erase the fact that the capture was worked, or the
inbox would quietly re-open a decision that was already made.

No unique constraint on anything. The same person may well be captured twice
from two places, and refusing the second one at the moment of capture is the
opposite of frictionless. De-duplication is its own task (PLAN.md, T-dedupe)
and belongs at triage, not here.

Nothing to backfill; there was nowhere a capture could previously have lived.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-09-22 09:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m3n4o5p6q7r8"
down_revision: str | Sequence[str] | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "captures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # What was typed, pasted or shared. Not null and never rewritten: the
        # parsed name and url are guesses, this is the thing that was actually
        # in hand.
        sa.Column("raw", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        # Plain text, constrained to ContactSource by the Pydantic schema, so
        # it can be handed straight to the contact on convert.
        sa.Column("source", sa.String(), nullable=True),
        # new / converted / dismissed. One column, not a done flag beside a
        # reason — same rule as deals.stage.
        sa.Column("status", sa.String(), server_default="new", nullable=False),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_captures_user_id"), "captures", ["user_id"], unique=False)
    # What the inbox, the nav badge and the briefing all filter on.
    op.create_index(op.f("ix_captures_status"), "captures", ["status"], unique=False)
    op.create_index(op.f("ix_captures_contact_id"), "captures", ["contact_id"], unique=False)
    op.create_index(op.f("ix_captures_deal_id"), "captures", ["deal_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Drops the inbox outright. Everything a capture became — the contact, the
    deal, the logged interaction — is a row in its own table and survives;
    what is lost is the record of where those came from.
    """
    op.drop_index(op.f("ix_captures_deal_id"), table_name="captures")
    op.drop_index(op.f("ix_captures_contact_id"), table_name="captures")
    op.drop_index(op.f("ix_captures_status"), table_name="captures")
    op.drop_index(op.f("ix_captures_user_id"), table_name="captures")
    op.drop_table("captures")
