from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

# The nine record types with a history: app/audit.py files each under its
# model's name, lower-cased.
EntityType = Literal[
    "contact",
    "organization",
    "deal",
    "task",
    "interaction",
    "project",
    "document",
    "watch",
    "capture",
]

# What happened. "update" carries the fields it changed; archive and restore
# change only whether the record is in use, so they carry none.
AuditAction = Literal["update", "archive", "restore"]


class FieldChange(BaseModel):
    """One field's value before and after, as JSON holds it.

    Amounts come back as strings and dates as ISO 8601, the same spelling the
    record itself uses. Link lists (`contact_ids`, ...) are sorted id lists.
    """

    old: Any
    new: Any


class AuditEventRead(BaseModel):
    id: UUID
    entity_type: EntityType
    entity_id: UUID
    action: AuditAction
    # Who made the change; None once that user no longer exists.
    actor_id: UUID | None
    # Only the fields that changed, keyed by their API name.
    changes: dict[str, FieldChange]
    created_at: datetime

    model_config = {"from_attributes": True}
