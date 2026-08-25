from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import Contact

# An interaction can involve several people (a meeting with two contacts), so the
# link is many-to-many — same pattern as project_contacts.
interaction_contacts = Table(
    "interaction_contacts",
    Base.metadata,
    Column("interaction_id", ForeignKey("interactions.id", ondelete="CASCADE"), primary_key=True),
    Column("contact_id", ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
)


class Interaction(Base):
    """A touchpoint with contacts: a call, meeting, mail or plain note.

    occurred_at in the past = activity log entry; in the future = a planned
    mail or meeting. `done` marks a planned entry as actually happened.
    """

    __tablename__ = "interactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    # Free-form column, constrained to the known set by the Pydantic schema.
    kind: Mapped[str] = mapped_column(String, default="note", server_default="note")
    subject: Mapped[str]
    notes: Mapped[str | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int | None]
    done: Mapped[bool] = mapped_column(default=False, server_default="false")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    contacts: Mapped[list[Contact]] = relationship(secondary=interaction_contacts, lazy="selectin")
