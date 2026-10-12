from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

TimelineItemType = Literal["interaction", "task", "deal", "document", "change"]


class TimelineItemRead(BaseModel):
    id: UUID
    item_type: TimelineItemType
    timestamp: datetime
    title: str
    description: str | None = None
    metadata: dict[str, Any] = {}
