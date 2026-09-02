"""attach documents and interactions to any record

Documents could only belong to a project and interactions only to contacts, so
a signed contract had nowhere to sit against its deal and "every call about this
deal" had no answer.

Six join tables rather than one polymorphic (target_type, target_id) column: a
polymorphic target cannot carry a foreign key, so deleting a deal would leave
rows pointing at nothing. CASCADE on both sides of every link — removing either
end drops the link row, never the document or interaction at the other end.

Nothing to backfill; the existing project_documents and interaction_contacts
tables are untouched.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-09-01 20:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j0k1l2m3n4o5"
down_revision: str | Sequence[str] | None = "i9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (join table, owning column, owning table, other column, other table)
LINKS = (
    ("document_contacts", "document_id", "documents", "contact_id", "contacts"),
    ("document_organizations", "document_id", "documents", "organization_id", "organizations"),
    ("document_deals", "document_id", "documents", "deal_id", "deals"),
    (
        "interaction_organizations",
        "interaction_id",
        "interactions",
        "organization_id",
        "organizations",
    ),
    ("interaction_deals", "interaction_id", "interactions", "deal_id", "deals"),
    ("interaction_projects", "interaction_id", "interactions", "project_id", "projects"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for name, own_column, own_table, other_column, other_table in LINKS:
        op.create_table(
            name,
            sa.Column(own_column, sa.Uuid(), nullable=False),
            sa.Column(other_column, sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint([own_column], [f"{own_table}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint([other_column], [f"{other_table}.id"], ondelete="CASCADE"),
            # The pair is the identity of a link, so the primary key also stops
            # the same document being attached to the same deal twice.
            sa.PrimaryKeyConstraint(own_column, other_column),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for name, *_ in reversed(LINKS):
        op.drop_table(name)
