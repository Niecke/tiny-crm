from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, ForeignKey, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.contact import Contact
from app.models.document import Document
from app.models.task import Task

project_contacts = Table(
    "project_contacts",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("contact_id", ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
)

project_tasks = Table(
    "project_tasks",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
)

project_documents = Table(
    "project_documents",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    description: Mapped[str | None]
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    contacts: Mapped[list[Contact]] = relationship(secondary=project_contacts, lazy="selectin")
    tasks: Mapped[list[Task]] = relationship(secondary=project_tasks, lazy="selectin")
    documents: Mapped[list[Document]] = relationship(secondary=project_documents, lazy="selectin")
