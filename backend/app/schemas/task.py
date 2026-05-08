from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime | None = None
    priority: int = 0


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime | None = None
    priority: int | None = None


class TaskRead(TaskCreate):
    id: UUID
    created: datetime
    updated: datetime

    model_config = {"from_attributes": True}
