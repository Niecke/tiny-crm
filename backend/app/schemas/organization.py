from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    name: str
    domain: str | None = None
    # Company-level contact details: the shared mailbox and the switchboard,
    # e.g. office@acme.example, rather than a person's own address.
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    industry: str | None = None
    notes: str | None = None


# PATCH uses the same fields but all optional — only sent fields are updated
class OrganizationUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    industry: str | None = None
    notes: str | None = None


class OrganizationRead(OrganizationCreate):
    id: UUID
    # How many contacts point here. Saves the list UI a request per row, and
    # answers "is this company worth keeping?" before a delete.
    contact_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
