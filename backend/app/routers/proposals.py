"""Review what agents propose (#321): list, count, approve, reject.

Session only (`current_active_user`): an API token can submit a proposal
(app/routers/agent.py) but can never decide one. Approving applies the change
through the same code the web client's own routes run, in the one transaction
that marks the proposal approved — so a change that fails leaves the CRM and
the proposal exactly as they were.
"""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.api_tokens import ApiToken
from app.auth.users import User
from app.db import count_rows, get_session
from app.models.proposal import AgentProposal
from app.proposals import apply, current_values, reference_labels, validate_payload
from app.schemas.proposal import (
    EntityType,
    ProposalAction,
    ProposalApprove,
    ProposalCount,
    ProposalPage,
    ProposalRead,
    ProposalReject,
    ProposalStatus,
)

router = APIRouter(prefix="/proposals", tags=["proposals"])


def _read(
    proposal: AgentProposal,
    token_name: str | None,
    current: dict[UUID, tuple[str, dict[str, object]]],
) -> ProposalRead:
    label, values = current.get(proposal.id, (None, None))
    return ProposalRead(
        id=proposal.id,
        entity_type=cast(EntityType, proposal.entity_type),
        action=cast(ProposalAction, proposal.action),
        target_id=proposal.target_id,
        proposed_payload=proposal.proposed_payload,
        applied_payload=proposal.applied_payload,
        reason=proposal.reason,
        status=cast(ProposalStatus, proposal.status),
        rejection_reason=proposal.rejection_reason,
        created_at=proposal.created_at,
        reviewed_at=proposal.reviewed_at,
        token_name=token_name,
        current=values,
        target_label=label,
    )


async def _lock_pending(session: AsyncSession, proposal_id: UUID, user: User) -> AgentProposal:
    """The caller's proposal, locked, and still pending.

    404 whether it is missing or someone else's. The row lock makes a double
    click wait for the first request, which then finds it decided and gets 409.
    """
    proposal = await session.scalar(
        select(AgentProposal)
        .where(AgentProposal.id == proposal_id, AgentProposal.user_id == user.id)
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"This proposal was already {proposal.status}")
    return proposal


async def _token_name(session: AsyncSession, proposal: AgentProposal) -> str | None:
    if proposal.api_token_id is None:
        return None
    name: str | None = await session.scalar(
        select(ApiToken.name).where(ApiToken.id == proposal.api_token_id)
    )
    return name


@router.get("/", response_model=ProposalPage)
async def list_proposals(
    status: ProposalStatus = Query(default="pending"),
    entity_type: EntityType | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProposalPage:
    """The caller's proposals, oldest first: the ones waiting longest go stale."""
    q = select(AgentProposal).where(
        AgentProposal.user_id == user.id, AgentProposal.status == status
    )
    if entity_type is not None:
        q = q.where(AgentProposal.entity_type == entity_type)
    total = await count_rows(session, q)
    result = await session.execute(
        q.add_columns(ApiToken.name)
        .outerjoin(ApiToken, ApiToken.id == AgentProposal.api_token_id)
        .order_by(AgentProposal.created_at.asc(), AgentProposal.id.asc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    proposals = [proposal for proposal, _name in rows]
    current = await current_values(session, proposals)
    labels = await reference_labels(session, proposals, current, user)
    return ProposalPage(
        items=[_read(proposal, name, current) for proposal, name in rows],
        total=total,
        skip=skip,
        limit=limit,
        labels=labels,
    )


# Declared above /{proposal_id} routes, as in app/routers/captures.py: a UUID
# path parameter would otherwise answer "count" with a 422.
@router.get("/count", response_model=ProposalCount)
async def count_proposals(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProposalCount:
    """How many are waiting: the nav badge, without pulling the rows."""
    pending = select(AgentProposal).where(
        AgentProposal.user_id == user.id, AgentProposal.status == "pending"
    )
    return ProposalCount(pending=await count_rows(session, pending))


@router.post("/{proposal_id}/approve", response_model=ProposalRead)
async def approve_proposal(
    proposal_id: UUID,
    body: ProposalApprove | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProposalRead:
    """Apply the change and mark it approved, or change nothing at all.

    With a `payload` the reviewer's edit is applied instead of the agent's, and
    kept in `applied_payload`; `version` refuses the approval (409) if the target
    changed since the reviewer loaded it. An error from the change itself raises
    before the one commit below, so the session rolls back and the proposal
    stays pending.
    """
    body = body or ProposalApprove()
    proposal = await _lock_pending(session, proposal_id, user)
    entity_type = cast(EntityType, proposal.entity_type)
    payload = proposal.proposed_payload
    if body.payload is not None:
        payload = validate_payload(entity_type, cast(ProposalAction, proposal.action), body.payload)
    target_id = await apply(session, proposal, payload, user, body.version)
    proposal.status = "approved"
    proposal.reviewed_at = datetime.now(UTC)
    if body.payload is not None:
        proposal.applied_payload = payload
    if proposal.action == "create":
        proposal.target_id = target_id
    token_name = await _token_name(session, proposal)
    await session.commit()
    await session.refresh(proposal)
    return _read(proposal, token_name, {})


@router.post("/{proposal_id}/reject", response_model=ProposalRead)
async def reject_proposal(
    proposal_id: UUID,
    body: ProposalReject | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProposalRead:
    """Dismiss it, with an optional note. No CRM data changes."""
    body = body or ProposalReject()
    proposal = await _lock_pending(session, proposal_id, user)
    proposal.status = "rejected"
    proposal.rejection_reason = body.rejection_reason
    proposal.reviewed_at = datetime.now(UTC)
    token_name = await _token_name(session, proposal)
    await session.commit()
    await session.refresh(proposal)
    return _read(proposal, token_name, {})
