from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# What an agent may propose changes to, and what it may propose doing. Strings
# in the column, enforced by the Literals in app/schemas/proposal.py — the same
# trade as Capture.status and AuditEvent.action.
ENTITY_TYPES = ("contact", "organization", "deal", "task", "interaction")
ACTIONS = ("create", "update", "archive")
# `pending` is the only state anything can still happen to; the other two are
# endings, like a capture that is converted or dismissed.
STATUSES = ("pending", "approved", "rejected")


class AgentProposal(Base):
    """A change an agent wants made, waiting for the operator to say yes (#321).

    An agent never writes to the CRM. It stages a create, update or archive
    here, and the change reaches the real table only when the operator approves
    it in the Approvals page — through the same code the session routes run, in
    the same transaction that marks this row approved.

    Plain `Base`, not `Record`: a proposal is a queue entry, not a record a
    person edits. It is never archived and never versioned; once decided it is
    simply history.
    """

    __tablename__ = "agent_proposals"
    __table_args__ = (
        # The inbox and the nav badge both ask "this user's proposals in this
        # status, oldest first".
        Index("ix_agent_proposals_user_status", "user_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    # Which token submitted it, for provenance. SET NULL: revoking only sets
    # `revoked_at`, so the name stays readable, and nothing deletes a token but
    # the account itself.
    api_token_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("api_tokens.id", ondelete="SET NULL")
    )

    entity_type: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")

    # The record an update or archive is about; for a create, the record that
    # approval made. No foreign key: it points at one of five tables, like
    # AuditEvent.entity_id.
    target_id: Mapped[UUID | None]

    # Exactly what the agent sent (normalised), never rewritten: it is the
    # provenance. What the reviewer actually applied after editing, if they
    # did, goes in `applied_payload`.
    proposed_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    applied_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # The agent's own account of why — "Extracted from conference notes".
    reason: Mapped[str] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
