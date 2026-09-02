from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

InteractionKind = Literal["call", "meeting", "email", "note", "other"]


class InteractionLinks(BaseModel):
    """What an interaction was about. All independent, all optional.

    Contacts were the only link an interaction could have, so "every call about
    this deal" had no answer. A kickoff call is with people, about a deal, under
    a project — all three at once.
    """

    contact_ids: list[UUID] = []
    organization_ids: list[UUID] = []
    deal_ids: list[UUID] = []
    project_ids: list[UUID] = []


class InteractionCreate(InteractionLinks):
    kind: InteractionKind = "note"
    subject: str
    notes: str | None = None
    # Future timestamps are planned interactions, past ones the activity log.
    occurred_at: datetime
    duration_minutes: int | None = None
    done: bool = False
    tags: list[str] = []


class InteractionUpdate(BaseModel):
    kind: InteractionKind | None = None
    subject: str | None = None
    notes: str | None = None
    occurred_at: datetime | None = None
    duration_minutes: int | None = None
    done: bool | None = None
    tags: list[str] | None = None
    # Whole-list replacement; an empty list detaches everything.
    contact_ids: list[UUID] | None = None
    organization_ids: list[UUID] | None = None
    deal_ids: list[UUID] | None = None
    project_ids: list[UUID] | None = None


class InteractionRead(InteractionLinks):
    id: UUID
    kind: InteractionKind
    subject: str
    notes: str | None
    occurred_at: datetime
    duration_minutes: int | None
    done: bool
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
