from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.interaction import Interaction


class Task(Base):
    """A to-do, optionally repeating, optionally about someone.

    A recurring task is not rescheduled in place: completing one creates the
    next instance and leaves this row done, so "did I actually check in March?"
    stays answerable. `recurrence_parent_id` chains the instances together and
    keeps a second completion of the same row from spawning a duplicate.

    A CRM follow-up is always about something — "call Maria back on Thursday",
    "chase the ACME proposal", "send what I promised on that call" — so a task
    can point at a contact, a deal and the interaction it came out of. All three
    are independent and all three are optional: a plain to-do links to nothing.
    """

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    title: Mapped[str]
    description: Mapped[str | None]
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[int] = mapped_column(default=0)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    done: Mapped[bool] = mapped_column(default=False, server_default="false")
    # One of app.recurrence.RECURRENCE_RULES, or NULL for a one-off task. Free-form
    # in the database, constrained to the known set by the Pydantic schema — same
    # pattern as Interaction.kind.
    recurrence_rule: Mapped[str | None]
    recurrence_interval: Mapped[int] = mapped_column(default=1, server_default="1")
    recurrence_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SET NULL, not CASCADE: deleting last month's instance must not take the
    # rest of the series with it.
    recurrence_parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )

    # What the task is about. SET NULL on all three, like every other link in
    # the app: deleting the person, the deal or the call must not silently drop
    # work the operator committed to. The task survives, unattached.
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    deal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), index=True
    )
    # The touchpoint this task came out of — "send the deck we talked about".
    interaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL"), index=True
    )

    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # selectin, not lazy: a task list always renders what each task is about, so
    # lazy loading would be three extra queries per row instead of per page.
    contact: Mapped[Contact | None] = relationship(lazy="selectin")
    deal: Mapped[Deal | None] = relationship(lazy="selectin")
    interaction: Mapped[Interaction | None] = relationship(lazy="selectin")

    @property
    def contact_name(self) -> str | None:
        """Denormalised for reads, so a task list needs no second request."""
        return self.contact.name if self.contact is not None else None

    @property
    def deal_title(self) -> str | None:
        return self.deal.title if self.deal is not None else None

    @property
    def interaction_subject(self) -> str | None:
        return self.interaction.subject if self.interaction is not None else None
