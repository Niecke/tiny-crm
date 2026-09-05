"""contact fields a business actually files

Adds the fields an address book needs before it can send a letter, an invoice
or an approach: job title, second email and phone, website, lifecycle status,
relation type, source, preferred language, birthday, the known day rate and
its currency, and whether this party works with freelancers at all.

Also splits the single free-text `address` into street / postal code / city /
country. The old value moves into `street` **verbatim** — no parsing. Splitting
"Hauptstraße 1, 1010 Wien" by guessing where the postcode starts is how a CRM
posts an invoice to the wrong place, and the operator can move the parts across
in a few seconds per contact with the data still in front of them.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-09-05 10:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l2m3n4o5p6q7"
down_revision: str | Sequence[str] | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All nullable: every one of them is genuinely unknown for a contact typed in
# from a business card. works_with_freelancers is nullable *on purpose* — see
# the model: False and "never asked" are different answers.
NEW_COLUMNS = (
    ("job_title", sa.String()),
    ("email_secondary", sa.String()),
    ("phone_secondary", sa.String()),
    ("website", sa.String()),
    ("street", sa.String()),
    ("postal_code", sa.String()),
    ("city", sa.String()),
    ("country", sa.String(length=2)),
    ("lifecycle_status", sa.String()),
    ("relation_type", sa.String()),
    ("source", sa.String()),
    ("preferred_language", sa.String(length=2)),
    ("birthday", sa.Date()),
    ("known_day_rate", sa.Numeric(precision=14, scale=2)),
    ("rate_currency", sa.String(length=3)),
    ("works_with_freelancers", sa.Boolean()),
)

# The two the contact list is scoped by. The rest wait for T31.
INDEXED = ("lifecycle_status", "relation_type")

# Rebuilds one line out of the parts on the way down. nullif keeps a contact
# with no address at all from getting an empty string where it had NULL.
_REJOIN_ADDRESS = """
UPDATE contacts
SET address = nullif(
    concat_ws(
        ', ',
        nullif(btrim(street), ''),
        nullif(btrim(postal_code), ''),
        nullif(btrim(city), ''),
        nullif(btrim(country), '')
    ),
    ''
)
"""


def upgrade() -> None:
    """Upgrade schema."""
    for column, column_type in NEW_COLUMNS:
        op.add_column("contacts", sa.Column(column, column_type, nullable=True))
    for column in INDEXED:
        op.create_index(op.f(f"ix_contacts_{column}"), "contacts", [column], unique=False)

    # The whole old value, unparsed, into the one part that can hold anything.
    op.execute(
        """
        UPDATE contacts
        SET street = address
        WHERE address IS NOT NULL AND btrim(address) <> ''
        """
    )
    op.drop_column("contacts", "address")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("contacts", sa.Column("address", sa.String(), nullable=True))
    op.execute(_REJOIN_ADDRESS)

    for column in INDEXED:
        op.drop_index(op.f(f"ix_contacts_{column}"), table_name="contacts")
    for column, _ in reversed(NEW_COLUMNS):
        op.drop_column("contacts", column)
