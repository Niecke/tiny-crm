from uuid import UUID

from pydantic import BaseModel

from app.schemas.contact import ContactCreate
from app.schemas.organization import OrganizationCreate


class CardContactDraft(BaseModel):
    """The person on the card, as read. Unchecked: the operator corrects it
    before anything is filed."""

    name: str | None = None
    job_title: str | None = None
    email: str | None = None
    email_secondary: str | None = None
    phone: str | None = None
    phone_secondary: str | None = None
    website: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    # Only ever two upper-case letters; anything else the model returned is
    # dropped rather than handed on to fail validation later.
    country: str | None = None
    notes: str | None = None


class CardOrganizationDraft(BaseModel):
    """The company on the card, as read."""

    name: str
    domain: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None


class OrganizationMatch(BaseModel):
    """A company already on file that the card most likely belongs to."""

    id: UUID
    name: str
    # What it was matched on: the same domain is near-certain, the same name
    # only likely.
    matched_on: str


class BusinessCardScan(BaseModel):
    contact: CardContactDraft
    # None when the card names no company.
    organization: CardOrganizationDraft | None = None
    match: OrganizationMatch | None = None


class BusinessCardImport(BaseModel):
    """The corrected card, filed in one go.

    Either `organization` — a company to create and file the contact under —
    or `contact.organization_id` for one already on file, or neither. Never
    both: that would be two answers to which company this is.
    """

    contact: ContactCreate
    organization: OrganizationCreate | None = None
