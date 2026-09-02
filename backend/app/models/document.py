from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, String, Table, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.organization import Organization

if TYPE_CHECKING:
    # Runtime import would be a cycle: project.py imports this module. The
    # relationship below resolves "Project" through SQLAlchemy's registry
    # instead, so only the annotation needs the name.
    from app.models.project import Project


def _link_table(name: str, other: str, other_table: str) -> Table:
    """A document-to-something join table.

    One real table per pair rather than a polymorphic (target_type, target_id)
    column: a polymorphic target cannot carry a foreign key, so deleting a deal
    would leave rows pointing at nothing. CASCADE on both sides — deleting
    either end removes the link, never the document at the other end of it.
    """
    return Table(
        name,
        Base.metadata,
        Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        Column(other, ForeignKey(f"{other_table}.id", ondelete="CASCADE"), primary_key=True),
    )


# A signed contract belongs to a deal, an NDA to a contact or the company it was
# signed with. Documents used to attach to projects and nothing else.
document_contacts = _link_table("document_contacts", "contact_id", "contacts")
document_organizations = _link_table("document_organizations", "organization_id", "organizations")
document_deals = _link_table("document_deals", "deal_id", "deals")


class Document(Base):
    """A stored file, attachable to any record it is actually about."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    title: Mapped[str]
    description: Mapped[str | None]
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    format: Mapped[str]
    size: Mapped[int]
    storage_key: Mapped[str]
    preview_key: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Many-to-many throughout: one framework agreement can cover two deals, and
    # the same NDA is filed against both the person and their company.
    contacts: Mapped[list[Contact]] = relationship(secondary=document_contacts, lazy="selectin")
    organizations: Mapped[list[Organization]] = relationship(
        secondary=document_organizations, lazy="selectin"
    )
    deals: Mapped[list[Deal]] = relationship(secondary=document_deals, lazy="selectin")
    # The pre-existing link, now editable from this side too. secondary is given
    # by table *name* so this module needs no import of project.py.
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        secondary="project_documents",
        back_populates="documents",
        lazy="selectin",
    )

    # The API speaks in ids; these keep DocumentRead a plain model_validate
    # instead of a hand-written converter.
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
