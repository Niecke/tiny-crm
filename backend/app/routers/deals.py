from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.models.contact import Contact
from app.models.deal import (
    ACTIVE_STAGES,
    DECIDED_STAGES,
    FINISHED_STAGES,
    OPEN_STAGES,
    WON_STAGES,
    Deal,
)
from app.models.organization import Organization
from app.schemas.deal import (
    DealCreate,
    DealRead,
    DealStage,
    DealStageChange,
    DealStatus,
    DealUpdate,
)
from app.schemas.page import Page

router = APIRouter(prefix="/deals", tags=["deals"])

# The pricing half of a deal. Kept together because they are validated as a set:
# which of them may be non-null depends entirely on value_type.
VALUE_FIELDS = (
    "value_type",
    "fixed_value",
    "rate",
    "rate_unit",
    "estimated_volume",
    "volume_unit",
)

_STAGES_BY_STATUS: dict[str, tuple[str, ...]] = {
    "open": OPEN_STAGES,
    "active": ACTIVE_STAGES,
    "won": WON_STAGES,
    "finished": FINISHED_STAGES,
}


async def _check_links(
    session: AsyncSession,
    contact_id: UUID | None,
    organization_id: UUID | None,
    user: User,
) -> None:
    """Refuse a contact or organization that is missing or someone else's.

    The FKs alone would accept any existing id, filing a deal against another
    tenant's customer — and leaking that customer's name back on every read.
    Same check contacts.py runs on organization_id, for the same reason.
    """
    if contact_id is not None:
        contact = await session.get(Contact, contact_id)
        if contact is None or contact.user_id != user.id:
            raise HTTPException(status_code=404, detail="Contact not found")
    if organization_id is not None:
        organization = await session.get(Organization, organization_id)
        if organization is None or organization.user_id != user.id:
            raise HTTPException(status_code=404, detail="Organization not found")


def _reject_orphan_lost_reason(stage: str, lost_reason: str | None) -> None:
    """A lost reason on a deal that is not lost is a contradiction, not a note."""
    if lost_reason is not None and stage != "lost":
        raise HTTPException(
            status_code=422,
            detail=f"lost_reason is only valid with stage 'lost', not '{stage}'",
        )


def _fields_foreign_to(value_type: str) -> tuple[str, ...]:
    """The pricing fields that make no sense for this way of pricing a deal."""
    if value_type == "fixed":
        return ("rate", "rate_unit", "estimated_volume", "volume_unit")
    return ("fixed_value",)


def _reject_contradictory_value(
    value_type: str,
    fixed_value: Decimal | None,
    rate: Decimal | None,
    rate_unit: str | None,
    estimated_volume: Decimal | None,
    volume_unit: str | None,
) -> None:
    """Refuse a deal that claims to be priced two ways at once.

    A row carrying both a contract sum and a day rate cannot be summed into a
    pipeline without picking one and ignoring the other, which is the ambiguity
    value_type exists to remove.
    """
    supplied = {
        "fixed_value": fixed_value,
        "rate": rate,
        "rate_unit": rate_unit,
        "estimated_volume": estimated_volume,
        "volume_unit": volume_unit,
    }
    for field in _fields_foreign_to(value_type):
        if supplied[field] is not None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} is not valid on a deal priced as '{value_type}'",
            )

    # A number with no unit cannot be multiplied by anything, and cannot be read
    # back either — "60" is not an estimate.
    if rate is not None and rate_unit is None:
        raise HTTPException(status_code=422, detail="rate_unit is required when a rate is given")
    if estimated_volume is not None and volume_unit is None:
        raise HTTPException(
            status_code=422,
            detail="volume_unit is required when an estimated volume is given",
        )


def _decided_side(stage: str) -> str | None:
    """Which way a decided stage went, or None while it is still being competed for."""
    if stage not in DECIDED_STAGES:
        return None
    return "lost" if stage == "lost" else "won"


def _apply_stage(deal: Deal, stage: str, lost_reason: str | None) -> None:
    """Move a deal to `stage` and bring everything that depends on it along.

    The single place a stage is ever assigned. Both PATCH and the stage endpoint
    route through here, so the two can never apply different rules — which is
    the whole reason the stage endpoint exists rather than a bare PATCH.
    """
    previous = deal.stage
    deal.stage = stage

    if stage in DECIDED_STAGES:
        # `closed_at` is when the deal was *decided*, so winning it stamps the
        # date and starting or finishing the work afterwards does not move it.
        # Flipping between won and lost is a new decision, so that does.
        if _decided_side(previous) != _decided_side(stage) or deal.closed_at is None:
            deal.closed_at = datetime.now(UTC)
        # A settled deal is 100% or 0%. Anything else leaves a weighted pipeline
        # forecasting money that is already banked, or already gone.
        deal.probability = 0 if stage == "lost" else 100
        deal.lost_reason = lost_reason if stage == "lost" else None
    else:
        # Back in play, so the decision and its reason go with it.
        deal.closed_at = None
        deal.lost_reason = None


@router.get("/", response_model=Page[DealRead])
async def list_deals(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    stage: DealStage | None = Query(default=None),
    # Coarser than `stage`: what am I competing for (`open`), what is on my
    # plate (`active` — open plus won and running), what came off (`won`), and
    # what is done with (`finished`).
    status: DealStatus | None = Query(default=None),
    contact_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[DealRead]:
    q = select(Deal).where(Deal.user_id == user.id)
    if search:
        q = q.where(Deal.title.ilike(f"%{search}%"))
    if stage is not None:
        q = q.where(Deal.stage == stage)
    if status is not None:
        q = q.where(Deal.stage.in_(_STAGES_BY_STATUS[status]))
    if contact_id is not None:
        q = q.where(Deal.contact_id == contact_id)
    if organization_id is not None:
        q = q.where(Deal.organization_id == organization_id)

    total = await count_rows(session, q)
    # Soonest expected close first, because that is the order the operator has
    # to work them in. A deal with no date is not urgent, so it sorts last
    # rather than first, which is where NULLs would land by default on ASC.
    # id breaks the tie so paging stays stable.
    result = await session.execute(
        q.order_by(nulls_last(Deal.expected_close_date.asc()), Deal.id.asc())
        .offset(skip)
        .limit(limit)
    )
    return Page[DealRead](
        items=[DealRead.model_validate(d) for d in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{deal_id}", response_model=DealRead)
async def get_deal(
    deal_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Deal:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("/", response_model=DealRead, status_code=201)
async def create_deal(
    body: DealCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Deal:
    await _check_links(session, body.contact_id, body.organization_id, user)
    _reject_orphan_lost_reason(body.stage, body.lost_reason)
    _reject_contradictory_value(
        body.value_type,
        body.fixed_value,
        body.rate,
        body.rate_unit,
        body.estimated_volume,
        body.volume_unit,
    )

    deal = Deal(**body.model_dump(), user_id=user.id)
    # A deal can be entered already won, or already running — work agreed before
    # anyone opened the CRM — so the decided-stage bookkeeping runs on create.
    _apply_stage(deal, body.stage, body.lost_reason)

    session.add(deal)
    await session.commit()
    # Reloads expected_value, which Postgres generates rather than the app.
    await session.refresh(deal)
    return deal


@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal(
    deal_id: UUID,
    body: DealUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Deal:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Deal not found")

    # exclude_unset=True — only update fields the caller actually sent
    updates = body.model_dump(exclude_unset=True)
    if "contact_id" in updates or "organization_id" in updates:
        await _check_links(
            session,
            updates.get("contact_id"),
            updates.get("organization_id"),
            user,
        )

    _merge_value_fields(deal, updates)

    # stage and lost_reason are handed to _apply_stage instead of being set
    # directly, so a stage change made through PATCH obeys the same rules as one
    # made through the stage endpoint.
    stage = updates.pop("stage", deal.stage)
    if "lost_reason" in updates:
        # Only a reason the caller actually sent is checked. One already on a
        # deal that is now being won or reopened gets cleared, not rejected.
        lost_reason = updates.pop("lost_reason")
        _reject_orphan_lost_reason(stage, lost_reason)
    else:
        lost_reason = deal.lost_reason

    for field, value in updates.items():
        setattr(deal, field, value)
    # Runs last, so a probability sent alongside a close is overridden by the
    # 100/0 the decided stage implies rather than the other way round.
    _apply_stage(deal, stage, lost_reason)

    await session.commit()
    await session.refresh(deal)
    return deal


def _merge_value_fields(deal: Deal, updates: dict[str, Any]) -> None:
    """Validate the pricing fields as they will be *after* this PATCH.

    A PATCH that sets `rate` on a fixed-price deal has to be refused even though
    the request itself mentions no value_type, so the check runs against the
    merged row rather than against what was sent.

    Switching value_type drops the other shape's fields in the same request:
    that is a deliberate re-pricing, not a contradiction. Sending the foreign
    field explicitly alongside the switch still fails.
    """
    merged: dict[str, Any] = {
        field: updates.get(field, getattr(deal, field)) for field in VALUE_FIELDS
    }

    new_type = merged["value_type"]
    if "value_type" in updates and updates["value_type"] != deal.value_type:
        for field in _fields_foreign_to(new_type):
            if field not in updates:
                merged[field] = None
                updates[field] = None

    _reject_contradictory_value(**merged)


@router.post("/{deal_id}/stage", response_model=DealRead)
async def change_stage(
    deal_id: UUID,
    body: DealStageChange,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Deal:
    """Move a deal along the pipeline.

    Its own endpoint rather than a PATCH field because moving stage is the one
    edit with consequences — it stamps `closed_at`, pins the probability and
    takes the lost reason — and because it is what a kanban drag calls.
    """
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Deal not found")

    _reject_orphan_lost_reason(body.stage, body.lost_reason)
    _apply_stage(deal, body.stage, body.lost_reason)

    await session.commit()
    await session.refresh(deal)
    return deal


@router.delete("/{deal_id}", status_code=204)
async def delete_deal(
    deal_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Deal not found")
    await session.delete(deal)
    await session.commit()
