from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from app.schemas.common import Currency, Money

# How far along we are with this party.
LifecycleStatus = Literal["lead", "prospect", "customer", "former"]

# What this party is to me. Deliberately a second field rather than more values
# on LifecycleStatus: "partner we have not approached yet" needs both halves.
RelationType = Literal[
    "customer",
    "partner",
    "subcontracting_target",
    "contracting_authority",
]

# Where they came from.
ContactSource = Literal[
    "referral",
    "inbound",
    "outbound",
    "event",
    "job_board",
    "tender_portal",
    "other",
]

# ISO 3166-1 alpha-2, upper-cased so "at" and "AT" are one country.
CountryCode = Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{2}$")]
# ISO 639-1, lower-cased. A language to write in, not a locale.
LanguageCode = Annotated[str, StringConstraints(to_lower=True, pattern=r"^[A-Za-z]{2}$")]

# The tri-state filter for `works_with_freelancers`. A plain bool query
# parameter could only ask two of the three questions, and "never asked" is the
# one that produces the next approach.
FreelancerAnswer = Literal["yes", "no", "unknown"]


class ContactCreate(BaseModel):
    name: str
    job_title: str | None = None
    organization_id: UUID | None = None
    email: str | None = None
    email_secondary: str | None = None
    phone: str | None = None
    phone_secondary: str | None = None
    website: str | None = None

    # The postal address in parts, so it can feed a letter, an invoice or a
    # vCard. Nothing can split a free-text blob back out afterwards.
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: CountryCode | None = None

    lifecycle_status: LifecycleStatus | None = None
    relation_type: RelationType | None = None
    source: ContactSource | None = None
    preferred_language: LanguageCode | None = None
    birthday: date | None = None

    # The rate as heard. Refused without its currency by the router — the same
    # rule that refuses a deal's volume with no unit.
    known_day_rate: Money | None = None
    rate_currency: Currency | None = None
    # None means never asked, which is not the same answer as False.
    works_with_freelancers: bool | None = None

    tags: list[str] = []
    notes: str | None = None


# PATCH uses the same fields but all optional — only sent fields are updated
class ContactUpdate(BaseModel):
    name: str | None = None
    job_title: str | None = None
    organization_id: UUID | None = None
    email: str | None = None
    email_secondary: str | None = None
    phone: str | None = None
    phone_secondary: str | None = None
    website: str | None = None

    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: CountryCode | None = None

    lifecycle_status: LifecycleStatus | None = None
    relation_type: RelationType | None = None
    source: ContactSource | None = None
    preferred_language: LanguageCode | None = None
    birthday: date | None = None

    known_day_rate: Money | None = None
    rate_currency: Currency | None = None
    works_with_freelancers: bool | None = None

    tags: list[str] | None = None
    notes: str | None = None


# ContactRead is what the API returns — includes server-generated fields
class ContactRead(ContactCreate):
    id: UUID
    # Read-only mirror of the linked organization's name, so a contact list can
    # show the company without a second request. Writes go through
    # organization_id.
    organization_name: str | None = None
    # Serialised as a string, like every other amount in the API: a binary
    # double cannot hold 0.10. See core/money_text.dart on the Dart side.
    known_day_rate: Decimal | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}  # lets Pydantic read SQLAlchemy model instances
