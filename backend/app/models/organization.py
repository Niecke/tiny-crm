from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Organization(Base):
    """A company a contact belongs to.

    Replaces the free-text `Contact.company`: two spellings of one customer used
    to be two companies, and nothing could be filed against the company itself.
    """

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    domain: Mapped[str | None]
    # The switchboard and the shared mailbox — info@, office@ — belong to the
    # company, not to any one person there.
    email: Mapped[str | None]
    phone: Mapped[str | None]
    address: Mapped[str | None]
    industry: Mapped[str | None]
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
