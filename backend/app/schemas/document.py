from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, computed_field


class DocumentLinks(BaseModel):
    """What a document is filed against. All independent, all optional.

    A signed contract belongs to a deal, an NDA to the person *and* the company
    it was signed with — so these are lists, and a document can sit under
    several records at once without being copied.
    """

    contact_ids: list[UUID] = []
    organization_ids: list[UUID] = []
    deal_ids: list[UUID] = []
    project_ids: list[UUID] = []


class DocumentRead(DocumentLinks):
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
    # Sent as a whole list, like the project router's link fields: the list
    # replaces what was there, and an empty list detaches everything.
    contact_ids: list[UUID] | None = None
    organization_ids: list[UUID] | None = None
    deal_ids: list[UUID] | None = None
    project_ids: list[UUID] | None = None
