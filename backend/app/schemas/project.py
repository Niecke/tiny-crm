from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    start_date: date
    end_date: date | None = None
    contact_ids: list[UUID] = []
    task_ids: list[UUID] = []
    document_ids: list[UUID] = []


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    contact_ids: list[UUID] | None = None
    task_ids: list[UUID] | None = None
    document_ids: list[UUID] | None = None


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    start_date: date
    end_date: date | None
    contact_ids: list[UUID]
    task_ids: list[UUID]
    document_ids: list[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
