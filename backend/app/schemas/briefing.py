"""The morning briefing as JSON, for the dashboard's "Today" section.

Not the full read models: each item carries what a line of the Slack briefing
shows, plus the day count the briefing computes in the operator's timezone.
The client renders these numbers rather than deriving them, so the dashboard
and the 07:00 message can never disagree about what is late (DASHBOARD.md,
rule 4).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.interaction import InteractionKind


class BriefingTask(BaseModel):
    id: UUID
    title: str
    due_date: datetime | None
    # 0 low · 1 normal · 2 high, as on the task itself.
    priority: int
    contact_name: str | None
    deal_title: str | None
    repeats: bool
    # Whole calendar days before today; 0 for a task due today.
    days_late: int


class BriefingInteraction(BaseModel):
    id: UUID
    kind: InteractionKind
    subject: str
    occurred_at: datetime
    duration_minutes: int | None
    # Who it is with: the linked contacts, or the organizations when no
    # contact is linked — the same fallback the Slack line uses.
    with_names: list[str]
    # 0 for today's plan; for an unconfirmed entry, how long ago it was due.
    days_late: int


class BriefingWatch(BaseModel):
    id: UUID
    name: str
    url: str
    organization_name: str | None
    next_due_at: datetime
    # Never swept is its own state, not "very overdue": the first sweep has no
    # schedule to be late against.
    never_swept: bool
    days_late: int


class BriefingCapture(BaseModel):
    id: UUID
    # The parsed name, or the raw text when parsing found none.
    display_name: str
    url: str | None
    note: str | None
    created_at: datetime
    # Calendar days since it was captured; 0 for today.
    days_waiting: int


class BriefingRead(BaseModel):
    # The day this is for, and whose day: echoed so a client can say "today"
    # and mean the same day the briefing meant.
    date: date
    timezone: str
    overdue_tasks: list[BriefingTask]
    tasks_today: list[BriefingTask]
    interactions_today: list[BriefingInteraction]
    unconfirmed_interactions: list[BriefingInteraction]
    watches_due: list[BriefingWatch]
    captures_waiting: list[BriefingCapture]
