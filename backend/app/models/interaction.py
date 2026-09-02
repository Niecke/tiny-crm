from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.organization import Organization

if TYPE_CHECKING:
    # Runtime import would be a cycle: project.py imports task.py, which imports
    # this module. The relationship resolves "Project" through SQLAlchemy's
    # registry instead, so only the annotation needs the name.
    from app.models.project import Project


def _link_table(name: str, other: str, other_table: str) -> Table:
    """An interaction-to-something join table. See document.py for the why."""
    return Table(
        name,
        Base.metadata,
        Column(
            "interaction_id", ForeignKey("interactions.id", ondelete="CASCADE"), primary_key=True
        ),
        Column(other, ForeignKey(f"{other_table}.id", ondelete="CASCADE"), primary_key=True),
    )


# An interaction can involve several people (a meeting with two contacts), so the
# link is many-to-many — same pattern as project_contacts.
interaction_contacts = _link_table("interaction_contacts", "contact_id", "contacts")
# A kickoff call is about a deal and happens under a project. Before this an
# interaction could only point at people, so "every call about this deal" had no
# answer.
interaction_organizations = _link_table(
    "interaction_organizations", "organization_id", "organizations"
)
interaction_deals = _link_table("interaction_deals", "deal_id", "deals")
interaction_projects = _link_table("interaction_projects", "project_id", "projects")


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
    organizations: Mapped[list[Organization]] = relationship(
        secondary=interaction_organizations, lazy="selectin"
    )
    deals: Mapped[list[Deal]] = relationship(secondary=interaction_deals, lazy="selectin")
    projects: Mapped[list["Project"]] = relationship(
        "Project", secondary=interaction_projects, lazy="selectin"
    )

    # The API speaks in ids; these keep InteractionRead a plain model_validate.
    @property
    def contact_ids(self) -> list[UUID]:
        return [c.id for c in self.contacts]

    @property
    def organization_ids(self) -> list[UUID]:
        return [o.id for o in self.organizations]

    @property
    def deal_ids(self) -> list[UUID]:
        return [d.id for d in self.deals]

    @property
    def project_ids(self) -> list[UUID]:
        return [p.id for p in self.projects]
