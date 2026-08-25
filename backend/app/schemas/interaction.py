from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

InteractionKind = Literal["call", "meeting", "email", "note", "other"]


class InteractionCreate(BaseModel):
    kind: InteractionKind = "note"
    subject: str
    notes: str | None = None
    # Future timestamps are planned interactions, past ones the activity log.
    occurred_at: datetime
    duration_minutes: int | None = None
    done: bool = False
    tags: list[str] = []
    contact_ids: list[UUID] = []


class InteractionUpdate(BaseModel):
    kind: InteractionKind | None = None
    subject: str | None = None
    notes: str | None = None
    occurred_at: datetime | None = None
    duration_minutes: int | None = None
    done: bool | None = None
    tags: list[str] | None = None
    contact_ids: list[UUID] | None = None


class InteractionRead(BaseModel):
    id: UUID
    kind: InteractionKind
    subject: str
    notes: str | None
    occurred_at: datetime
    duration_minutes: int | None
    done: bool
    tags: list[str]
    contact_ids: list[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
