from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    company: Mapped[str | None]
    email: Mapped[str | None]
    phone: Mapped[str | None]
    address: Mapped[str | None]
    # PostgreSQL native array — stored as text[], queried as a Python list
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    notes: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
