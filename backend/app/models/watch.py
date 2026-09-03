from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import Organization

# What kind of source this is. Free-form column constrained to the known set by
# the Pydantic schema — same choice as Interaction.kind and Deal.stage.
#
# The two that matter most are *not* companies: a job board with a saved search
# and a tender portal are sources you sweep, not parties you have a relationship
# with. A careers page is the special case where the source does have an
# organization behind it.
WATCH_KINDS = ("job_board", "careers_page", "tender_portal", "other")

# What a sweep turned up. "nothing" is the normal, valuable answer — it is what
# makes a year of diligence on a quiet portal provable.
CHECK_OUTCOMES = ("nothing", "found")


class Watch(Base):
    """A source swept on a cadence: a job board, a careers page, a tender portal.

    The intake end of the pipeline. Everything from Deal onward records
    opportunities that already exist; this is where they come from.
    """

    __tablename__ = "watches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    url: Mapped[str]
    kind: Mapped[str] = mapped_column(String, default="other", server_default="other", index=True)

    # The saved search in words: keywords, CPV codes, region — the filters the
    # URL encodes. A query string is unreadable six months later.
    query_note: Mapped[str | None]
    notes: Mapped[str | None]

    # Set for a careers page, null for a portal. Deliberately not enforced per
    # kind: finding a company you have not filed yet is normal, and refusing the
    # watch until you do is backwards. SET NULL, like every other link here.
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )

    # The cadence, reusing the rule set and arithmetic from app/recurrence.py —
    # the same closed dropdown, the same month-end clamping, and the same
    # "next due is computed from the check, not the missed slot" rule. What it
    # does *not* reuse is Task: one task per watch would bury the real
    # follow-ups under twenty identical "check X" rows.
    recurrence_rule: Mapped[str]
    recurrence_interval: Mapped[int] = mapped_column(default=1, server_default="1")

    # Stamped together whenever a check is logged, and nowhere else, so they
    # cannot drift from the WatchCheck history they summarise. Stored rather
    # than derived because the list has to sort and page by "most overdue" in
    # SQL, and month-clamping arithmetic does not belong in a query.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Pause a source without deleting it and losing its history.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization | None] = relationship(lazy="selectin")

    @property
    def organization_name(self) -> str | None:
        """Denormalised for reads, so a watch list needs no second request."""
        return self.organization.name if self.organization is not None else None


class WatchCheck(Base):
    """One sweep of one watch. Append-only.

    Not a `last_checked_at` column overwritten each time, for the reason
    recurring tasks already commit to — "did I actually check in March?" — and
    one more: a source that has produced nothing in a year has to look
    different from a fresh one, which a single timestamp cannot show.
    """

    __tablename__ = "watch_checks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    # CASCADE: the log is part of the watch, not an independent record.
    watch_id: Mapped[UUID] = mapped_column(ForeignKey("watches.id", ondelete="CASCADE"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # One of CHECK_OUTCOMES.
    outcome: Mapped[str] = mapped_column(String, default="nothing", server_default="nothing")
    note: Mapped[str | None]

    # What this find turned into, so the source of a win stays traceable back to
    # the sweep that found it. SET NULL, not CASCADE: deleting the deal must not
    # erase the record of having found it.
    created_deal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), index=True
    )
    created_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def found(self) -> bool:
        return self.outcome == "found"
