"""create deals table

Adds the pipeline: an opportunity, how it is priced, where it stands, and —
once decided — when it closed and why it was lost. Nothing to backfill; there
was no earlier place a deal could have been recorded.

`expected_value` is a stored generated column rather than an application field,
so it cannot drift from the columns it derives from, and a pipeline total can
SUM it directly. It is NULL — never 0 — when no total can be derived.

Revision ID: 4b7e2d91c6fa
Revises: 3f9a1c47b2d8
Create Date: 2026-08-31 18:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b7e2d91c6fa"
down_revision: str | Sequence[str] | None = "3f9a1c47b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Units are deliberately never converted: multiplying a day rate by a volume
# estimated in months would need an invented days-per-month constant.
EXPECTED_VALUE_SQL = """
CASE
    WHEN value_type = 'fixed' THEN fixed_value
    WHEN rate IS NOT NULL
     AND estimated_volume IS NOT NULL
     AND rate_unit = volume_unit
        THEN round(rate * estimated_volume, 2)
    ELSE NULL
END
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        # How the deal is priced. Plain text, constrained by the Pydantic schema.
        sa.Column("value_type", sa.String(), server_default="fixed", nullable=False),
        # Numeric, not double precision: a pipeline summed from binary floats
        # drifts away from the invoices it is meant to predict.
        sa.Column("fixed_value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("rate", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("rate_unit", sa.String(), nullable=True),
        # NULL is meaningful: the engagement is genuinely open-ended.
        sa.Column("estimated_volume", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("volume_unit", sa.String(), nullable=True),
        # Unconstrained precision so no product of rate and volume overflows it.
        sa.Column(
            "expected_value",
            sa.Numeric(),
            sa.Computed(EXPECTED_VALUE_SQL, persisted=True),
            nullable=True,
        ),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        # Plain text, constrained to the known stages by the Pydantic schema —
        # a native enum would make adding a stage an ALTER TYPE migration.
        sa.Column("stage", sa.String(), server_default="lead", nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("probability", sa.Integer(), nullable=True),
        sa.Column("lost_reason", sa.String(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
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
        # SET NULL on both: losing the person or the company must never delete
        # the record of what was sold to them.
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deals_user_id"), "deals", ["user_id"], unique=False)
    # The columns every pipeline query filters or sorts on.
    op.create_index(op.f("ix_deals_stage"), "deals", ["stage"], unique=False)
    op.create_index(
        op.f("ix_deals_expected_close_date"), "deals", ["expected_close_date"], unique=False
    )
    op.create_index(op.f("ix_deals_contact_id"), "deals", ["contact_id"], unique=False)
    op.create_index(op.f("ix_deals_organization_id"), "deals", ["organization_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_deals_organization_id"), table_name="deals")
    op.drop_index(op.f("ix_deals_contact_id"), table_name="deals")
    op.drop_index(op.f("ix_deals_expected_close_date"), table_name="deals")
    op.drop_index(op.f("ix_deals_stage"), table_name="deals")
    op.drop_index(op.f("ix_deals_user_id"), table_name="deals")
    op.drop_table("deals")
