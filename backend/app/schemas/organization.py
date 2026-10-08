from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import VersionedUpdate


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
class OrganizationUpdate(VersionedUpdate):
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
    # Set once the record has been archived: out of every list, read-only, and
    # still reachable by its id. NULL for everything in use.
    archived_at: datetime | None = None
    # Goes up by one on every save. Send it back on PATCH to have the save
    # refused if someone else saved first; see VersionedUpdate.
    version: int

    model_config = {"from_attributes": True}
