from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Label, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.links import load_scoped
from app.models.deal import Deal
from app.models.organization import Organization
from app.models.task import Task
from app.models.watch import Watch, WatchCheck
from app.recurrence import RecurrenceRule, next_due_date
from app.schemas.page import Page
from app.schemas.watch import (
    WatchCheckCreate,
    WatchCheckRead,
    WatchCheckResult,
    WatchCreate,
    WatchKind,
    WatchRead,
    WatchUpdate,
)

router = APIRouter(prefix="/watches", tags=["watches"])


def _count_column(outcome: str | None) -> Label[int]:
    """Checks logged against a watch, as a correlated subquery.

    One extra column on the list query instead of a request per row — the same
    trick organizations use for contact_count. `found_count` is what answers
    "has this source ever actually produced anything?".
    """
    q = select(func.count(WatchCheck.id)).where(WatchCheck.watch_id == Watch.id)
    if outcome is not None:
        q = q.where(WatchCheck.outcome == outcome)
    label = "found_count" if outcome == "found" else "check_count"
    return q.correlate(Watch).scalar_subquery().label(label)


async def _counts(session: AsyncSession, watch_id: UUID) -> tuple[int, int]:
    """(found_count, check_count) for one watch."""
    row = (
        await session.execute(
            select(
                func.count(WatchCheck.id).filter(WatchCheck.outcome == "found"),
                func.count(WatchCheck.id),
            ).where(WatchCheck.watch_id == watch_id)
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


def _to_read(watch: Watch, found_count: int, check_count: int) -> WatchRead:
    return WatchRead(
        id=watch.id,
        name=watch.name,
        url=watch.url,
        kind=cast(WatchKind, watch.kind),
        query_note=watch.query_note,
        notes=watch.notes,
        organization_id=watch.organization_id,
        organization_name=watch.organization_name,
        recurrence_rule=cast(RecurrenceRule, watch.recurrence_rule),
        recurrence_interval=watch.recurrence_interval,
        last_checked_at=watch.last_checked_at,
        next_due_at=watch.next_due_at,
        active=watch.active,
        found_count=found_count,
        check_count=check_count,
        created_at=watch.created_at,
        updated_at=watch.updated_at,
    )


async def _get_owned(session: AsyncSession, watch_id: UUID, user: User) -> Watch:
    watch = await session.get(Watch, watch_id)
    if watch is None or watch.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watch not found")
    return watch


async def _check_organization(
    session: AsyncSession, organization_id: UUID | None, user: User
) -> None:
    """Refuse an organization that is missing or belongs to someone else.

    The FK alone would accept any existing id, filing a watch under another
    tenant's company and leaking that company's name back on every read.
    """
    if organization_id is not None:
        await load_scoped(session, Organization, [organization_id], user.id)


@router.get("/", response_model=Page[WatchRead])
async def list_watches(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    kind: WatchKind | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    # The sweep list: only what is due now or overdue.
    due: bool | None = Query(default=None),
    # None returns paused sources as well as running ones.
    active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[WatchRead]:
    q = select(Watch).where(Watch.user_id == user.id)
    if search:
        q = q.where(Watch.name.ilike(f"%{search}%"))
    if kind is not None:
        q = q.where(Watch.kind == kind)
    if organization_id is not None:
        q = q.where(Watch.organization_id == organization_id)
    if active is not None:
        q = q.where(Watch.active.is_(active))
    if due is not None:
        now = datetime.now(UTC)
        q = q.where(Watch.next_due_at <= now if due else Watch.next_due_at > now)

    total = await count_rows(session, q)
    # Most overdue first — the order the sweep is actually worked in. Paused
    # sources sink to the bottom rather than sitting at the top pretending to be
    # 200 days late. id breaks the tie so paging stays stable.
    result = await session.execute(
        q.add_columns(_count_column("found"), _count_column(None))
        .order_by(Watch.active.desc(), Watch.next_due_at.asc(), Watch.id.asc())
        .offset(skip)
        .limit(limit)
    )
    return Page[WatchRead](
        items=[_to_read(w, found, checks) for w, found, checks in result.all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{watch_id}", response_model=WatchRead)
async def get_watch(
    watch_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> WatchRead:
    watch = await _get_owned(session, watch_id, user)
    return _to_read(watch, *await _counts(session, watch.id))


@router.post("/", response_model=WatchRead, status_code=201)
async def create_watch(
    body: WatchCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> WatchRead:
    await _check_organization(session, body.organization_id, user)

    data = body.model_dump()
    # A source that has never been swept is due now, so it shows up in the
    # first "what's due today" rather than hiding for a cadence.
    data["next_due_at"] = data["next_due_at"] or datetime.now(UTC)

    watch = Watch(**data, user_id=user.id)
    session.add(watch)
    await session.commit()
    await session.refresh(watch)
    return _to_read(watch, 0, 0)


@router.patch("/{watch_id}", response_model=WatchRead)
async def update_watch(
    watch_id: UUID,
    body: WatchUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> WatchRead:
    watch = await _get_owned(session, watch_id, user)

    updates = body.model_dump(exclude_unset=True)
    if "organization_id" in updates:
        await _check_organization(session, updates["organization_id"], user)

    cadence_changed = any(f in updates for f in ("recurrence_rule", "recurrence_interval"))
    for field, value in updates.items():
        setattr(watch, field, value)

    # Re-anchor on the last sweep when the cadence itself changed, unless the
    # caller set a due date explicitly. Leaving the old date would keep a watch
    # switched from monthly to weekly on its monthly schedule.
    #
    # Only once it has actually been swept: a source that has never been checked
    # is still unchecked whatever its cadence, and recomputing here would push a
    # brand new watch out of "due today" just for editing it.
    if cadence_changed and "next_due_at" not in updates and watch.last_checked_at is not None:
        watch.next_due_at = _next_due(watch, watch.last_checked_at, watch.last_checked_at)

    await session.commit()
    await session.refresh(watch)
    return _to_read(watch, *await _counts(session, watch.id))


def _next_due(watch: Watch, anchor: datetime, checked_at: datetime) -> datetime:
    """When this watch is next due, one cadence step on from `anchor`.

    Straight through app/recurrence.py, so a watch swept three weeks late is
    due once rather than three times, and monthly cadences clamp to the end of
    short months. `until` is never passed: a watch runs until it is paused, so
    the series cannot run out and the result is never None.

    The anchor differs by caller, and getting it wrong is subtle. Logging a
    sweep anchors on the *scheduled* date, which is what keeps a cadence on its
    rhythm — due on the 1st, swept on the 28th, due the 1st again. Changing the
    cadence anchors on the *last sweep* instead: `next_due_at` by then already
    holds a date the old cadence produced, and stepping from it would carry the
    old rhythm into the new rule.
    """
    due = next_due_date(
        anchor,
        cast(RecurrenceRule, watch.recurrence_rule),
        watch.recurrence_interval,
        completed_at=checked_at,
    )
    if due is None:  # unreachable without `until`; an assert would vanish under -O
        raise RuntimeError("a watch series cannot run out")
    return due


@router.post("/{watch_id}/check", response_model=WatchCheckResult, status_code=201)
async def log_check(
    watch_id: UUID,
    body: WatchCheckCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> WatchCheckResult:
    """Record one sweep, move the watch on, and optionally capture what it found.

    One endpoint rather than three calls because the three belong together: a
    check that logged but failed to advance the cadence would come straight back
    as due, and a deal created separately could end up with no check pointing at
    it. Everything here commits or nothing does.
    """
    watch = await _get_owned(session, watch_id, user)

    if body.outcome != "found" and (body.create_deal or body.create_task):
        raise HTTPException(
            status_code=422,
            detail="create_deal and create_task need outcome 'found'",
        )

    checked_at = body.checked_at or datetime.now(UTC)

    deal: Deal | None = None
    if body.create_deal is not None:
        # The watch's own company is the obvious default — a careers page or a
        # contracting authority is already filed against one.
        organization_id = body.create_deal.organization_id or watch.organization_id
        await _check_organization(session, organization_id, user)
        # A plain deal for now. Once T38 lands, a tender_portal watch will set
        # deal_kind=tender here and carry the submission deadline into it.
        deal = Deal(
            user_id=user.id,
            title=body.create_deal.title,
            expected_close_date=body.create_deal.expected_close_date,
            organization_id=organization_id,
            notes=body.create_deal.notes,
        )
        session.add(deal)

    task: Task | None = None
    if body.create_task is not None:
        task = Task(
            user_id=user.id,
            title=body.create_task.title,
            due_date=body.create_task.due_date,
        )
        session.add(task)

    # The link columns below need real ids.
    await session.flush()

    check = WatchCheck(
        user_id=user.id,
        watch_id=watch.id,
        checked_at=checked_at,
        outcome=body.outcome,
        note=body.note,
        created_deal_id=deal.id if deal is not None else None,
        created_task_id=task.id if task is not None else None,
    )
    session.add(check)

    # Stamped here and nowhere else, so they cannot drift from the log.
    watch.last_checked_at = checked_at
    watch.next_due_at = _next_due(watch, watch.next_due_at, checked_at)

    await session.commit()
    await session.refresh(check)
    await session.refresh(watch)
    return WatchCheckResult(
        check=WatchCheckRead.model_validate(check),
        watch=_to_read(watch, *await _counts(session, watch.id)),
    )


@router.get("/{watch_id}/checks", response_model=Page[WatchCheckRead])
async def list_checks(
    watch_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[WatchCheckRead]:
    """This source's history, newest first. Append-only: there is no edit."""
    await _get_owned(session, watch_id, user)

    q = select(WatchCheck).where(WatchCheck.watch_id == watch_id, WatchCheck.user_id == user.id)
    total = await count_rows(session, q)
    result = await session.execute(
        q.order_by(WatchCheck.checked_at.desc(), WatchCheck.id.asc()).offset(skip).limit(limit)
    )
    return Page[WatchCheckRead](
        items=[WatchCheckRead.model_validate(c) for c in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.delete("/{watch_id}", status_code=204)
async def delete_watch(
    watch_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    """Deleting a watch takes its check history with it (CASCADE).

    Pausing with `active=false` is the non-destructive option, and what the UI
    offers first.
    """
    watch = await _get_owned(session, watch_id, user)
    await session.delete(watch)
    await session.commit()
