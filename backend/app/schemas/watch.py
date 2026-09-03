from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.recurrence import MAX_RECURRENCE_INTERVAL, RecurrenceRule

WatchKind = Literal["job_board", "careers_page", "tender_portal", "other"]
CheckOutcome = Literal["nothing", "found"]


class WatchCreate(BaseModel):
    name: str
    # Required: a source you cannot open is not a source.
    url: str
    kind: WatchKind = "other"
    query_note: str | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    recurrence_rule: RecurrenceRule
    recurrence_interval: int = Field(default=1, ge=1, le=MAX_RECURRENCE_INTERVAL)
    active: bool = True
    # Defaults to now, so a source that has never been swept shows up in
    # "what's due" immediately. Set it to skip the first sweep when the watch
    # is added right after checking the site by hand.
    next_due_at: datetime | None = None


class WatchUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    kind: WatchKind | None = None
    query_note: str | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    recurrence_rule: RecurrenceRule | None = None
    recurrence_interval: int | None = Field(default=None, ge=1, le=MAX_RECURRENCE_INTERVAL)
    active: bool | None = None
    next_due_at: datetime | None = None


class WatchRead(BaseModel):
    id: UUID
    name: str
    url: str
    kind: WatchKind
    query_note: str | None
    notes: str | None
    organization_id: UUID | None
    # Denormalised so a list row shows the company without a request per row.
    organization_name: str | None
    recurrence_rule: RecurrenceRule
    recurrence_interval: int
    last_checked_at: datetime | None
    next_due_at: datetime
    active: bool
    # How many sweeps have ever turned something up. The question a single
    # timestamp cannot answer: is this source worth keeping?
    found_count: int
    check_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WatchFindDeal(BaseModel):
    """A deal created straight from a find.

    Deliberately narrow — a title, when it closes, who it is with. Pricing and
    the rest belong in the deal form, which is one tap away; the point here is
    to capture the find before the browser tab is closed.
    """

    title: str
    expected_close_date: date | None = None
    # Defaults to the watch's own organization when it has one.
    organization_id: UUID | None = None
    notes: str | None = None


class WatchFindTask(BaseModel):
    """A task created straight from a find. Same reasoning as WatchFindDeal."""

    title: str
    due_date: datetime | None = None


class WatchCheckCreate(BaseModel):
    """Body of POST /watches/{id}/check — one sweep of one source."""

    outcome: CheckOutcome = "nothing"
    note: str | None = None
    # Both refused unless the sweep actually found something: a deal created by
    # a check that found nothing is a contradiction, not a shortcut.
    create_deal: WatchFindDeal | None = None
    create_task: WatchFindTask | None = None
    # Overridable so a sweep done yesterday can be logged today without
    # pretending it happened now; the next due date is computed from it.
    checked_at: datetime | None = None


class WatchCheckRead(BaseModel):
    id: UUID
    watch_id: UUID
    checked_at: datetime
    outcome: CheckOutcome
    note: str | None
    created_deal_id: UUID | None
    created_task_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WatchCheckResult(BaseModel):
    """The logged sweep plus the watch it moved on."""

    check: WatchCheckRead
    watch: WatchRead
