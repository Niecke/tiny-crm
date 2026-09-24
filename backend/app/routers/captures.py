from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.captures import parse_capture
from app.db import count_rows, get_session
from app.models.capture import Capture
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.interaction import Interaction
from app.models.organization import Organization
from app.schemas.capture import (
    CaptureConvert,
    CaptureConvertResult,
    CaptureCount,
    CaptureCreate,
    CaptureRead,
    CaptureStatus,
    CaptureUpdate,
)
from app.schemas.contact import ContactRead
from app.schemas.deal import DealRead
from app.schemas.interaction import InteractionRead
from app.schemas.page import Page

router = APIRouter(prefix="/captures", tags=["captures"])


async def _check_organization(
    session: AsyncSession, organization_id: UUID | None, user: User
) -> None:
    """Refuse an organization_id that is missing or belongs to someone else.

    Same guard as the contacts router: without it the FK would accept any
    existing id, filing a freshly converted lead under another tenant's company
    and leaking that company's name back on every read.
    """
    if organization_id is None:
        return
    organization = await session.get(Organization, organization_id)
    if organization is None or organization.user_id != user.id:
        raise HTTPException(status_code=404, detail="Organization not found")


async def _get_owned(session: AsyncSession, capture_id: UUID, user: User) -> Capture:
    """The capture, or 404 — whether it is missing or simply someone else's.

    A 403 would confirm the id exists, which is one bit more than another
    tenant should learn. Same rule as every other router here.
    """
    capture = await session.get(Capture, capture_id)
    if capture is None or capture.user_id != user.id:
        raise HTTPException(status_code=404, detail="Capture not found")
    return capture


@router.get("/", response_model=Page[CaptureRead])
async def list_captures(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    # Defaults to the only list worth opening. `?status=all` widens it to
    # everything already worked, which is the "what did I do with that link?"
    # question rather than the daily one.
    status: CaptureStatus | Literal["all"] = Query(default="new"),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[CaptureRead]:
    q = select(Capture).where(Capture.user_id == user.id)
    if status != "all":
        q = q.where(Capture.status == status)
    if search:
        # Both columns, because half the rows have no name yet and the raw
        # text is the only thing those can be found by.
        q = q.where(or_(Capture.raw.ilike(f"%{search}%"), Capture.name.ilike(f"%{search}%")))

    total = await count_rows(session, q)
    # Oldest first, and this is the whole point of the screen: an inbox is a
    # queue to empty, not a feed to scroll. Newest-first would bury exactly the
    # captures that have been waiting longest, which are the ones going stale.
    result = await session.execute(
        q.order_by(Capture.created_at.asc(), Capture.id.asc()).offset(skip).limit(limit)
    )
    return Page[CaptureRead](
        items=[CaptureRead.model_validate(c) for c in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


# Declared above /{capture_id} on purpose: FastAPI matches in declaration
# order, and a UUID path parameter would otherwise swallow "count" and answer
# with a 422 about it not being a UUID.
@router.get("/count", response_model=CaptureCount)
async def count_captures(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> CaptureCount:
    """How many are waiting, and how long the oldest has been.

    One query for the badge rather than a page of rows nobody renders.
    """
    waiting = select(Capture).where(Capture.user_id == user.id, Capture.status == "new")
    total = await count_rows(session, waiting)
    oldest = await session.scalar(
        select(func.min(Capture.created_at)).where(
            Capture.user_id == user.id, Capture.status == "new"
        )
    )
    oldest_days = None if oldest is None else max(0, (datetime.now(UTC) - oldest).days)
    return CaptureCount(new=total, oldest_days=oldest_days)


@router.get("/{capture_id}", response_model=CaptureRead)
async def get_capture(
    capture_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Capture:
    return await _get_owned(session, capture_id, user)


@router.post("/", response_model=CaptureRead, status_code=201)
async def create_capture(
    body: CaptureCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Capture:
    """Park one line. The only required field is `raw`.

    Name and link are guessed here rather than in the client so the share
    target, the quick-add box and a curl from a phone shortcut all file the
    same thing.
    """
    name, url = parse_capture(body.raw)
    capture = Capture(
        user_id=user.id,
        raw=body.raw,
        # An explicitly supplied value wins over the guess — the share target
        # already knows the URL Android handed it.
        name=body.name if body.name is not None else name,
        url=body.url if body.url is not None else url,
        note=body.note,
        source=body.source,
    )
    session.add(capture)
    await session.commit()
    await session.refresh(capture)
    return capture


@router.patch("/{capture_id}", response_model=CaptureRead)
async def update_capture(
    capture_id: UUID,
    body: CaptureUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Capture:
    """Fix up a capture before working it.

    Re-editing `raw` does *not* re-run the parser: by the time anyone is
    editing, the name and url on the row are the corrected ones, and silently
    overwriting them from a re-typed line is exactly the cleverness `raw`
    exists to avoid.
    """
    capture = await _get_owned(session, capture_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(capture, field, value)
    await session.commit()
    await session.refresh(capture)
    return capture


@router.delete("/{capture_id}", status_code=204)
async def delete_capture(
    capture_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    """Remove it outright — what Undo in the quick-add box calls.

    Distinct from /dismiss, which keeps the row as a decision that was made.
    A typo is not a decision.
    """
    capture = await _get_owned(session, capture_id, user)
    await session.delete(capture)
    await session.commit()


def _reject_unless_new(capture: Capture) -> None:
    """Refuse to work a capture that has already been decided.

    409 rather than 404 or 422: the row exists and the request is well formed,
    the state is simply wrong. Converting twice would open a second deal on the
    same person and nothing would say why — the sort of quiet duplicate that
    only turns up when you write to someone for the second time.
    """
    if capture.status != "new":
        raise HTTPException(
            status_code=409,
            detail=f"This capture was already {capture.status}",
        )


@router.post("/{capture_id}/convert", response_model=CaptureConvertResult, status_code=201)
async def convert_capture(
    capture_id: UUID,
    body: CaptureConvert,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> CaptureConvertResult:
    """Work one capture: who they are, the lead it opens, the message you sent.

    One endpoint rather than four calls because the four belong together. A
    contact created without its deal is a name nobody follows up; a deal
    created without the capture being stamped comes straight back in tomorrow's
    inbox as still waiting. Everything here commits or nothing does — the same
    shape as POST /watches/{id}/check.
    """
    capture = await _get_owned(session, capture_id, user)
    _reject_unless_new(capture)

    contact: Contact
    if body.contact is not None:
        await _check_organization(session, body.contact.organization_id, user)
        contact = Contact(
            **body.contact.model_dump(exclude={"source"}),
            # The capture already knows where this person came from; the body
            # only has to say when it disagrees.
            source=body.contact.source or capture.source,
            user_id=user.id,
        )
        session.add(contact)
        # Before the deal, because Contact.id is generated by SQLAlchemy at
        # flush time and the deal needs a real one to point at. A deal filed
        # against nobody is the exact failure this endpoint exists to prevent.
        await session.flush()
    else:
        assert body.contact_id is not None  # the schema guarantees one or the other
        found = await session.get(Contact, body.contact_id)
        if found is None or found.user_id != user.id:
            raise HTTPException(status_code=404, detail="Contact not found")
        contact = found

    deal: Deal | None = None
    if body.deal is not None:
        await _check_organization(session, body.deal.organization_id, user)
        deal = Deal(
            user_id=user.id,
            title=body.deal.title,
            # Explicit even though it is the column default: a deal born from
            # the inbox is at the start of the pipeline by definition, and
            # saying so here is cheaper than inferring it later.
            stage="lead",
            # The lead is always against the person it came from. Without this
            # the deal board shows a title and no one to write to.
            contact_id=contact.id,
            expected_close_date=body.deal.expected_close_date,
            organization_id=body.deal.organization_id or contact.organization_id,
            notes=body.deal.notes,
        )
        session.add(deal)

    # The links below need a real deal id.
    await session.flush()

    interaction: Interaction | None = None
    if body.interaction is not None:
        occurred_at = body.interaction.occurred_at or datetime.now(UTC)
        interaction = Interaction(
            user_id=user.id,
            kind=body.interaction.kind,
            subject=body.interaction.subject,
            notes=body.interaction.notes,
            occurred_at=occurred_at,
            # Anything logged in the past already happened — the same rule the
            # interaction form applies. Without it the briefing would list
            # every outreach under "planned, never confirmed" the next morning.
            done=occurred_at <= datetime.now(UTC),
        )
        interaction.contacts.append(contact)
        if deal is not None:
            # So "every message about this lead" has an answer.
            interaction.deals.append(deal)
        session.add(interaction)

    capture.status = "converted"
    capture.triaged_at = datetime.now(UTC)
    capture.contact_id = contact.id
    capture.deal_id = deal.id if deal is not None else None

    await session.commit()
    await session.refresh(capture)
    await session.refresh(contact)
    if deal is not None:
        await session.refresh(deal)
    if interaction is not None:
        await session.refresh(interaction)

    return CaptureConvertResult(
        capture=CaptureRead.model_validate(capture),
        contact=ContactRead.model_validate(contact),
        deal=None if deal is None else DealRead.model_validate(deal),
        interaction=(None if interaction is None else InteractionRead.model_validate(interaction)),
    )


@router.post("/{capture_id}/dismiss", response_model=CaptureRead)
async def dismiss_capture(
    capture_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Capture:
    """Decide not to pursue this one.

    Kept rather than deleted: "I looked at this and said no" is an answer, and
    an inbox that forgets its own rejections offers them again next month.
    Use DELETE for a typo, which is not a decision.
    """
    capture = await _get_owned(session, capture_id, user)
    _reject_unless_new(capture)
    capture.status = "dismissed"
    capture.triaged_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(capture)
    return capture
