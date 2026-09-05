from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import Organization

# The classification columns below are free-form String, constrained to their
# value sets by the Literals in app/schemas/contact.py — the same choice as
# Deal.stage. A native Postgres enum would turn "add a status" into an ALTER
# TYPE migration, which is the wrong trade for sets the operator is still
# shaping, and one definition of each set beats two that can drift.


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    # What they do there, which is half of whether an approach is worth making:
    # "Head of Delivery" and "Werkstudent" are not the same conversation.
    job_title: Mapped[str | None]
    # Replaces the old free-text `company`. SET NULL rather than CASCADE: losing
    # the company must never silently delete the people who worked there.
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str | None]
    # The private address, the second number, the one that actually gets
    # answered. Filing it in `notes` is how a CRM loses a working channel.
    email_secondary: Mapped[str | None]
    phone: Mapped[str | None]
    phone_secondary: Mapped[str | None]
    website: Mapped[str | None]

    # --- Where the post goes ----------------------------------------------
    # Four columns, not one free-text blob: a letter, an invoice and a vCard
    # all need the parts separately, and nothing can split them back out
    # afterwards without guessing.
    street: Mapped[str | None]
    postal_code: Mapped[str | None]
    city: Mapped[str | None]
    # ISO 3166-1 alpha-2, upper-cased by the schema, so filtering by country
    # cannot split "AT", "at" and "Austria" into three countries.
    country: Mapped[str | None] = mapped_column(String(2))

    # --- Who they are to me ------------------------------------------------
    # Two columns, not one. Status is *how far along we are* (lead → prospect →
    # customer → former); type is *what this party is to me* (customer,
    # partner, subcontracting target, contracting authority). Collapsing them
    # loses "partner we have not approached yet", which is the row worth acting
    # on. Both are indexed like Deal.stage, because they are what the contact
    # list is scoped by; the remaining filter columns stay unindexed until T31
    # measures which ones are worth it on a table this size.
    lifecycle_status: Mapped[str | None] = mapped_column(String, index=True)
    relation_type: Mapped[str | None] = mapped_column(String, index=True)
    # Where they came from. job_board and tender_portal mirror T40's watch
    # kinds: a sweep that turns into a person is how those contacts arrive.
    source: Mapped[str | None] = mapped_column(String)
    # ISO 639-1, lower-cased by the schema. Which language to write the letter
    # in — not a locale, so no region subtag.
    preferred_language: Mapped[str | None] = mapped_column(String(2))
    birthday: Mapped[date | None] = mapped_column(Date)

    # --- The freelance half ------------------------------------------------
    # The rate as heard, not a quote and not a commitment — what this party pays
    # or charges, so an approach starts from a number instead of from nothing.
    # Numeric, never Float: binary floating point cannot hold 0.10.
    known_day_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Paired with the rate and refused without it: "800" is not a rate.
    rate_currency: Mapped[str | None] = mapped_column(String(3))
    # Nullable on purpose, and this is the whole point of the column: False is
    # "asked, and they don't", None is "never asked". A NOT NULL default would
    # answer the question for every contact that has never been approached, and
    # the never-asked ones are exactly the list worth working through.
    works_with_freelancers: Mapped[bool | None] = mapped_column(Boolean)

    # PostgreSQL native array — stored as text[], queried as a Python list
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # selectin, not lazy loading: a contact is almost always rendered with its
    # company name, and a list of 50 would otherwise be 50 extra queries.
    organization: Mapped[Organization | None] = relationship(lazy="selectin")

    @property
    def organization_name(self) -> str | None:
        """Denormalised for reads, so a contact list needs no second request."""
        return self.organization.name if self.organization is not None else None
