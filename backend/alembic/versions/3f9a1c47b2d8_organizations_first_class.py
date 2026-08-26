"""organizations as a first-class entity

Replaces the free-text `contacts.company` with a foreign key to a new
`organizations` table, backfilling one organization per distinct company name
per user. Matching is case-insensitive and ignores surrounding whitespace, so
"ACME", "acme " and "Acme" collapse into one company instead of three.

Revision ID: 3f9a1c47b2d8
Revises: 977164c0f298
Create Date: 2026-08-26 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f9a1c47b2d8"
down_revision: str | Sequence[str] | None = "977164c0f298"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("industry", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_user_id"), "organizations", ["user_id"], unique=False)

    op.add_column("contacts", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_contacts_organization_id"), "contacts", ["organization_id"], unique=False
    )
    op.create_foreign_key(
        "fk_contacts_organization_id_organizations",
        "contacts",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # One organization per distinct company spelling per user. min() picks a
    # stable representative name from the group — an arbitrary but repeatable
    # choice between "ACME" and "Acme"; the operator can rename it afterwards.
    op.execute(
        """
        INSERT INTO organizations (id, user_id, name, created_at, updated_at)
        SELECT gen_random_uuid(), c.user_id, min(btrim(c.company)), now(), now()
        FROM contacts c
        WHERE c.company IS NOT NULL AND btrim(c.company) <> ''
        GROUP BY c.user_id, lower(btrim(c.company))
        """
    )
    op.execute(
        """
        UPDATE contacts c
        SET organization_id = o.id
        FROM organizations o
        WHERE o.user_id = c.user_id
          AND c.company IS NOT NULL
          AND lower(o.name) = lower(btrim(c.company))
        """
    )

    op.drop_column("contacts", "company")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("contacts", sa.Column("company", sa.String(), nullable=True))
    # Write the company name back as free text before the link disappears.
    op.execute(
        """
        UPDATE contacts c
        SET company = o.name
        FROM organizations o
        WHERE o.id = c.organization_id
        """
    )

    op.drop_constraint("fk_contacts_organization_id_organizations", "contacts", type_="foreignkey")
    op.drop_index(op.f("ix_contacts_organization_id"), table_name="contacts")
    op.drop_column("contacts", "organization_id")

    op.drop_index(op.f("ix_organizations_user_id"), table_name="organizations")
    op.drop_table("organizations")
