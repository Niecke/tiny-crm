from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Task(Base):
    """A to-do, optionally repeating.

    A recurring task is not rescheduled in place: completing one creates the
    next instance and leaves this row done, so "did I actually check in March?"
    stays answerable. `recurrence_parent_id` chains the instances together and
    keeps a second completion of the same row from spawning a duplicate.
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
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
