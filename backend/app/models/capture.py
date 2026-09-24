from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import Contact
from app.models.deal import Deal

# Where a capture stands. One enum, not a pair of booleans — the same choice as
# Deal.stage, and for the same reason: two columns describing one state drift
# apart, and then "is this still waiting?" has two answers.
#
# There is no stage between `new` and the two endings on purpose. A capture is
# not a small pipeline; the pipeline is the Deal it becomes.
CAPTURE_STATUSES = ("new", "converted", "dismissed")
# Everything that still wants a decision. The inbox, the nav badge and the
# morning briefing all ask this one question.
OPEN_STATUSES = ("new",)


class Capture(Base):
    """A name or a link, parked in seconds, to be dealt with later.

    The hole this fills: `Contact` needs a name and rewards a dozen more
    fields, so a bare LinkedIn URL seen on a phone had nowhere to go and ended
    up somewhere outside the CRM, which is the same as nowhere.

    Deliberately not a half-filled `Contact`. A contact list that is mostly
    stubs is a contact list nobody trusts, and the filters that make it useful
    (`lifecycle_status`, `relation_type`, `works_with_freelancers`) all read as
    "never asked" on a stub, which is indistinguishable from a real answer.
    """

    __tablename__ = "captures"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)

    # Exactly what was typed, pasted or shared, and never rewritten.
    #
    # This is the column that makes the parse below safe to get wrong: `name`
    # and `url` are guesses, editable and occasionally nonsense, but whatever
    # was actually in hand at the moment of capture survives all of it. Losing
    # that is losing the capture.
    raw: Mapped[str]

    # Pulled out of `raw` by app/captures.py, then editable. Both nullable:
    # "https://…/in/someone" has no name worth guessing, and a name typed on
    # its own has no link.
    name: Mapped[str | None]
    url: Mapped[str | None]
    # Why this person was worth writing down — "spoke at the Vienna meetup".
    # A week later this is the difference between an approach and a cold stare.
    note: Mapped[str | None]
    # Free-form String constrained to ContactSource by the Pydantic schema, the
    # same trade as Contact.source: it is handed straight to the contact on
    # convert, so one definition of the set rather than two that can drift.
    source: Mapped[str | None] = mapped_column(String)

    status: Mapped[str] = mapped_column(String, default="new", server_default="new", index=True)
    # When it stopped being `new`. Only a timestamp — `status` is what anything
    # actually branches on, exactly as Deal.closed_at sits beside Deal.stage.
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # What it became. SET NULL on both, like Deal.contact_id: deleting the
    # person must never erase the record that this capture was worked, or the
    # inbox would quietly re-open decisions that were already made.
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    deal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # selectin for the same reason as Deal.contact: the inbox renders converted
    # rows with what they turned into, and a page of 50 would be 100 queries.
    contact: Mapped[Contact | None] = relationship(lazy="selectin")
    deal: Mapped[Deal | None] = relationship(lazy="selectin")

    @property
    def contact_name(self) -> str | None:
        """Denormalised for reads, so the inbox needs no second request."""
        return self.contact.name if self.contact is not None else None

    @property
    def deal_title(self) -> str | None:
        return self.deal.title if self.deal is not None else None

    @property
    def is_open(self) -> bool:
        """Still waiting for a decision."""
        return self.status in OPEN_STATUSES

    @property
    def display_name(self) -> str:
        """What to call this in a list, a badge or the briefing.

        Falls back to `raw` rather than to "Untitled": a capture always has
        *something* the operator recognises, because they typed it.
        """
        return self.name or self.raw
