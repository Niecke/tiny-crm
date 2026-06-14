from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, computed_field


class DocumentRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    tags: list[str]
    format: str
    size: int
    storage_key: str
    preview_key: str | None = Field(exclude=True)
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_preview(self) -> bool:
        return self.preview_key is not None

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
