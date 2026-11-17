from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

from app.schemas.page import Page

# Mirror ENTITY_TYPES, ACTIONS and STATUSES in app/models/proposal.py: one
# definition of each set that the API can enforce.
EntityType = Literal["contact", "organization", "deal", "task", "interaction"]
ProposalAction = Literal["create", "update", "archive"]
ProposalStatus = Literal["pending", "approved", "rejected"]

REASON_MAX_LENGTH = 2000


class ProposalCreate(BaseModel):
    """What an agent sends: a change, and why.

    `payload` holds exactly the fields of the entity's own Create (for a
    create) or Update (for an update) schema; app/proposals.py validates it
    against that schema, so a proposal can never hold something the real
    endpoint would refuse.
    """

    entity_type: EntityType
    action: ProposalAction
    target_id: UUID | None = None
    payload: dict[str, Any] = {}
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
    ]

    @model_validator(mode="after")
    def _target_matches_action(self) -> Self:
        if self.action == "create" and self.target_id is not None:
            raise ValueError("target_id must not be set for a create")
        if self.action != "create" and self.target_id is None:
            raise ValueError(f"target_id is required for an {self.action}")
        return self


class ProposalSubmitted(BaseModel):
    """The compact answer an agent gets back."""

    id: UUID
    status: ProposalStatus


class ProposalRead(BaseModel):
    id: UUID
    entity_type: EntityType
    action: ProposalAction
    # The record an update or archive is about; after a create is approved, the
    # record that approval made.
    target_id: UUID | None = None
    proposed_payload: dict[str, Any]
    # What was applied, when the reviewer edited the proposal before approving.
    applied_payload: dict[str, Any] | None = None
    reason: str
    status: ProposalStatus
    rejection_reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    # Provenance: the name of the token that submitted it, None once gone.
    token_name: str | None = None
    # For an update, the target's present values for the proposed fields plus
    # its `version`; for an archive, its `archived_at`. None for a create.
    current: dict[str, Any] | None = None
    target_label: str | None = None


class ProposalPage(Page[ProposalRead]):
    # id → name for every record the payloads and current values mention, so the
    # UI shows "ACME GmbH" where the payload holds a UUID.
    labels: dict[str, str] = {}


class ProposalApprove(BaseModel):
    """Approve as proposed (empty body), or with what the reviewer edited."""

    payload: dict[str, Any] | None = None
    # The version of the target the reviewer was looking at; the approval is
    # refused with 409 if the record has changed since.
    version: int | None = None


class ProposalReject(BaseModel):
    rejection_reason: str | None = None

    @field_validator("rejection_reason")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > REASON_MAX_LENGTH:
            raise ValueError(f"must be at most {REASON_MAX_LENGTH} characters")
        return value or None


class ProposalCount(BaseModel):
    pending: int
