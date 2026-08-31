from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import Organization


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    # Replaces the old free-text `company`. SET NULL rather than CASCADE: losing
    # the company must never silently delete the people who worked there.
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str | None]
    phone: Mapped[str | None]
    address: Mapped[str | None]
    # PostgreSQL native array — stored as text[], queried as a Python list
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # selectin, not lazy loading: a contact is almost always rendered with its
    # company name, and a list of 50 would otherwise be 50 extra queries.
    organization: Mapped[Organization | None] = relationship(lazy="selectin")

    @property
    def organization_name(self) -> str | None:
        """Denormalised for reads, so a contact list needs no second request."""
        return self.organization.name if self.organization is not None else None
