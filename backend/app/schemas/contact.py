from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ContactCreate(BaseModel):
    name: str
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tags: list[str] = []
    notes: str | None = None


# PATCH uses the same fields but all optional — only sent fields are updated
class ContactUpdate(BaseModel):
    name: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


# ContactRead is what the API returns — includes server-generated fields
class ContactRead(ContactCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}  # lets Pydantic read SQLAlchemy model instances
