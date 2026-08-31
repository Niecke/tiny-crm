from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.recurrence import MAX_RECURRENCE_INTERVAL, RecurrenceRule


def validate_recurrence(
    *,
    recurrence_rule: str | None,
    recurrence_until: datetime | None,
    due_date: datetime | None,
) -> None:
    """Reject recurrence settings that cannot produce a next instance.

    Called on the *merged* state — a PATCH may set the rule while the due date
    comes from the stored row, or clear the due date out from under a rule that
    is already there.
    """
    if recurrence_rule is None:
        if recurrence_until is not None:
            raise ValueError("recurrence_until needs a recurrence_rule")
        return
    if due_date is None:
        raise ValueError("A recurring task needs a due date to repeat from")
    if recurrence_until is not None and recurrence_until < due_date:
        raise ValueError("recurrence_until must not be before the due date")


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime | None = None
    priority: int = 0
    tags: list[str] = []
    done: bool = False
    recurrence_rule: RecurrenceRule | None = None
    recurrence_interval: int = Field(default=1, ge=1, le=MAX_RECURRENCE_INTERVAL)
    recurrence_until: datetime | None = None

    @model_validator(mode="after")
    def _recurrence_is_usable(self) -> Self:
        validate_recurrence(
            recurrence_rule=self.recurrence_rule,
            recurrence_until=self.recurrence_until,
            due_date=self.due_date,
        )
        return self


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime | None = None
    priority: int | None = None
    tags: list[str] | None = None
    done: bool | None = None
    recurrence_rule: RecurrenceRule | None = None
    recurrence_interval: int | None = Field(default=None, ge=1, le=MAX_RECURRENCE_INTERVAL)
    recurrence_until: datetime | None = None


class TaskRead(TaskCreate):
    id: UUID
    # The instance this one was spawned from, walking the series back through
    # its history. NULL for the first task of a series and for one-offs.
    recurrence_parent_id: UUID | None = None
    created: datetime
    updated: datetime

    model_config = {"from_attributes": True}


class TaskCompletionRead(TaskRead):
    """A patched task, plus the instance that completing it created.

    `next_occurrence` is only filled in on the response that created it, so the
    UI can say when the next one is due instead of guessing that a repeat
    happened (the series may have ended at `recurrence_until`).
    """

    next_occurrence: TaskRead | None = None
