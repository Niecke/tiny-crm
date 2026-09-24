from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

from app.schemas.contact import (
    ContactRead,
    ContactSource,
    LifecycleStatus,
    RelationType,
)
from app.schemas.deal import DealRead
from app.schemas.interaction import InteractionKind, InteractionRead

# Mirrors CAPTURE_STATUSES in app/models/capture.py. One definition of the set
# that the API can enforce, the same arrangement Deal.stage has.
CaptureStatus = Literal["new", "converted", "dismissed"]

# The whole input contract of the quick-add box. Stripped, because a trailing
# newline is what pasting from a phone gives you, and non-empty, because a
# blank capture is a row that can never be triaged and never be recognised.
RawCapture = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CaptureCreate(BaseModel):
    """One line, and nothing else required.

    `name` and `url` are accepted but almost never sent: the router fills them
    from `raw` via app/captures.py. They exist so the share-target page can
    pass the link Android already handed it separately, rather than
    re-concatenating it into a string for the parser to take apart again.
    """

    raw: RawCapture
    name: str | None = None
    url: str | None = None
    note: str | None = None
    source: ContactSource | None = None


class CaptureUpdate(BaseModel):
    """Fixing up a capture before working it.

    `status` is deliberately absent. It moves through /convert and /dismiss and
    nowhere else — the same funnel Deal.stage has through `_apply_stage`, so
    that arriving at an ending always stamps everything that ending implies.
    """

    raw: RawCapture | None = None
    name: str | None = None
    url: str | None = None
    note: str | None = None
    source: ContactSource | None = None


class CaptureRead(BaseModel):
    id: UUID
    raw: str
    name: str | None = None
    url: str | None = None
    note: str | None = None
    source: ContactSource | None = None
    status: CaptureStatus
    triaged_at: datetime | None = None
    contact_id: UUID | None = None
    deal_id: UUID | None = None
    # Read-only mirrors, so a triaged row can say what it became without the
    # inbox fetching each one. Writes happen through /convert.
    contact_name: str | None = None
    deal_title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CaptureCount(BaseModel):
    """What the nav badge and the briefing need, without pulling the rows.

    `oldest_days` is the half that makes the number mean something: "3 waiting"
    is a healthy inbox on Tuesday and a broken habit if the oldest is from
    March.
    """

    new: int
    oldest_days: int | None = None


class CaptureContact(BaseModel):
    """The person this capture turns out to be.

    A trimmed `ContactCreate`: the fields worth filling in while looking at a
    profile page, and no more. Everything else is one tap away on the contact
    itself, and a triage screen that asks for a postal address is a triage
    screen that gets skipped.

    `lifecycle_status` defaults to "lead" because that is what converting one
    of these means; it stays settable for the case where the person turns out
    to be an existing customer.
    """

    name: str
    job_title: str | None = None
    organization_id: UUID | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    lifecycle_status: LifecycleStatus | None = "lead"
    relation_type: RelationType | None = None
    # Defaults to the capture's own source when the body does not say.
    source: ContactSource | None = None
    birthday: date | None = None
    tags: list[str] = []
    notes: str | None = None


class CaptureDeal(BaseModel):
    """The lead this becomes. Deliberately narrow, like WatchFindDeal.

    No `stage`: converting a capture opens a deal at the start of the pipeline
    by definition. A deal that is already at "proposal" did not come from an
    inbox.
    """

    title: str
    expected_close_date: date | None = None
    organization_id: UUID | None = None
    notes: str | None = None


class CaptureInteraction(BaseModel):
    """The record that you wrote to them.

    This is the whole point of the triage session, so it is part of the same
    request rather than a second form: an outreach logged separately is an
    outreach that gets logged half the time.
    """

    kind: InteractionKind = "email"
    subject: str
    notes: str | None = None
    # Defaults to now. Overridable so a message actually sent last night can be
    # logged this morning without lying about when it happened.
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        """Read a timestamp with no offset as UTC.

        The convert route compares this against `datetime.now(UTC)` to decide
        whether the outreach has happened yet, and comparing a naive datetime
        with an aware one is a TypeError — a 500 on input that should simply be
        taken at face value. Everything this API stores is UTC, so a client
        that omitted the offset meant UTC.
        """
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class CaptureConvert(BaseModel):
    """Body of POST /captures/{id}/convert — one worked capture."""

    # Exactly one of these. Linking an existing contact is the "I already know
    # them" case, which is common enough that forcing a duplicate would be a
    # worse answer than asking.
    contact_id: UUID | None = None
    contact: CaptureContact | None = None
    # Both optional: some captures are worth filing as a person without opening
    # a deal, and some get written to later rather than now.
    deal: CaptureDeal | None = None
    interaction: CaptureInteraction | None = None

    @model_validator(mode="after")
    def _exactly_one_contact(self) -> Self:
        if (self.contact_id is None) == (self.contact is None):
            raise ValueError("send exactly one of contact_id or contact")
        return self


class CaptureConvertResult(BaseModel):
    """The worked capture and everything it produced.

    All four in one response so the triage screen can advance to the next item
    without a single follow-up request.
    """

    capture: CaptureRead
    contact: ContactRead
    deal: DealRead | None = None
    interaction: InteractionRead | None = None
