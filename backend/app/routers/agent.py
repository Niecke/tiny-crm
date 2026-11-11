"""The agent API (#320): read-only context for an external agent.

`/v1/agent/*`, public as `/api/v1/agent/*` (the ingress strips `/api`). Every
route authenticates with an API token and nothing else (app/auth/agent.py), and
returns the token owner's rows only. Compact output; see app/schemas/agent.py.

The one rule for this file: it never imports `current_active_user`, and no
session route imports `current_token_user`. That is the boundary that keeps a
read-only token away from everything a session can do.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.archive import live
from app.auth.agent import current_token_user
from app.auth.users import User
from app.briefing import DayWindow, briefing_queries
from app.config import settings
from app.db import get_session
from app.models import Contact, Deal, Interaction, Organization, Task
from app.models.deal import OPEN_STAGES
from app.models.interaction import interaction_contacts, interaction_organizations
from app.models.search import SEARCHABLES
from app.routers.briefing import current_time
from app.routers.search import MIN_QUERY_LENGTH, checked_terms, search_one
from app.schemas.agent import (
    AgentContact,
    AgentDeal,
    AgentHit,
    AgentInteraction,
    AgentOrganization,
    AgentOrgContact,
    AgentOrgDeal,
    AgentPipeline,
    AgentRef,
    AgentSearch,
    AgentTask,
    AgentTasks,
    HitType,
)

router = APIRouter(prefix="/v1/agent", tags=["agent"])

# Per type, so the whole answer stays small.
MAX_HITS = 20
RECENT_INTERACTIONS = 5
EXCERPT_LENGTH = 280
MAX_ORG_CONTACTS = 25
MAX_PIPELINE_DEALS = 200

# Searched in this order; the value is the hit's `type`.
_SEARCH_TYPES: dict[str, HitType] = {
    "contacts": "contact",
    "organizations": "organization",
    "deals": "deal",
}


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= EXCERPT_LENGTH:
        return collapsed or None
    return collapsed[:EXCERPT_LENGTH].rstrip() + "…"


def _or_none[T](items: list[T]) -> list[T] | None:
    return items or None


def _interactions(rows: list[Interaction]) -> list[AgentInteraction] | None:
    return _or_none(
        [
            AgentInteraction(
                id=i.id,
                kind=i.kind,
                subject=i.subject,
                occurred_at=i.occurred_at,
                done=i.done,
                notes_excerpt=_excerpt(i.notes),
            )
            for i in rows
        ]
    )


async def _recent_interactions(
    session: AsyncSession, user: User, link: Any, column: Any, entity_id: UUID
) -> list[AgentInteraction] | None:
    rows = await session.scalars(
        select(Interaction)
        .join(link, link.c.interaction_id == Interaction.id)
        .where(Interaction.user_id == user.id, column == entity_id, live(Interaction))
        .order_by(Interaction.occurred_at.desc(), Interaction.id)
        .limit(RECENT_INTERACTIONS)
        .options(raiseload("*"))
    )
    return _interactions(list(rows))


@router.get("/search", response_model=AgentSearch, response_model_exclude_none=True)
async def search(
    q: str = Query(min_length=MIN_QUERY_LENGTH, max_length=200),
    limit: int = Query(default=5, ge=1, le=MAX_HITS),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_token_user),
) -> AgentSearch:
    """Contacts, organizations and open deals matching every word of `q`."""
    terms = checked_terms(q)
    hits: list[AgentHit] = []
    for searchable in SEARCHABLES:
        hit_type = _SEARCH_TYPES.get(searchable.key)
        if hit_type is None:
            continue
        # A won or lost deal is history, not context for what to do next.
        where = [Deal.stage.in_(OPEN_STAGES)] if searchable.key == "deals" else []
        group = await search_one(session, searchable, user.id, terms, 0, limit, where=where)
        hits.extend(
            AgentHit(type=hit_type, id=h.id, title=h.title, subtitle=h.subtitle)
            for h in group.items
        )
    return AgentSearch(q=" ".join(terms), hits=hits)


@router.get("/contacts/{contact_id}", response_model=AgentContact, response_model_exclude_none=True)
async def get_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_token_user),
) -> AgentContact:
    """A contact's profile and their last interactions. Archived ones are flagged."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    organization = contact.organization
    return AgentContact(
        id=contact.id,
        name=contact.name,
        archived=True if contact.archived_at is not None else None,
        job_title=contact.job_title,
        organization=AgentRef(id=organization.id, name=organization.name)
        if organization is not None
        else None,
        email=contact.email,
        phone=contact.phone,
        city=contact.city,
        country=contact.country,
        lifecycle_status=contact.lifecycle_status,
        relation_type=contact.relation_type,
        tags=_or_none(list(contact.tags)),
        notes=contact.notes,
        recent_interactions=await _recent_interactions(
            session, user, interaction_contacts, interaction_contacts.c.contact_id, contact.id
        ),
    )


@router.get(
    "/organizations/{organization_id}",
    response_model=AgentOrganization,
    response_model_exclude_none=True,
)
async def get_organization(
    organization_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_token_user),
) -> AgentOrganization:
    """An organization with its people, open deals and last interactions."""
    organization = await session.get(Organization, organization_id)
    if organization is None or organization.user_id != user.id:
        raise HTTPException(status_code=404, detail="Organization not found")
    people = await session.scalars(
        select(Contact)
        .where(
            Contact.user_id == user.id, Contact.organization_id == organization.id, live(Contact)
        )
        .order_by(func.lower(Contact.name), Contact.id)
        .limit(MAX_ORG_CONTACTS)
        .options(raiseload("*"))
    )
    deals = await session.scalars(
        select(Deal)
        .where(
            Deal.user_id == user.id,
            Deal.organization_id == organization.id,
            Deal.stage.in_(OPEN_STAGES),
            live(Deal),
        )
        .order_by(Deal.stage_changed_at.desc(), Deal.id)
        .options(raiseload("*"))
    )
    return AgentOrganization(
        id=organization.id,
        name=organization.name,
        archived=True if organization.archived_at is not None else None,
        domain=organization.domain,
        email=organization.email,
        phone=organization.phone,
        industry=organization.industry,
        notes=organization.notes,
        contacts=_or_none(
            [AgentOrgContact(id=c.id, name=c.name, job_title=c.job_title) for c in people]
        ),
        open_deals=_or_none([AgentOrgDeal(id=d.id, title=d.title, stage=d.stage) for d in deals]),
        recent_interactions=await _recent_interactions(
            session,
            user,
            interaction_organizations,
            interaction_organizations.c.organization_id,
            organization.id,
        ),
    )


@router.get("/deals/open", response_model=AgentPipeline, response_model_exclude_none=True)
async def open_deals(
    now: datetime = Depends(current_time),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_token_user),
) -> AgentPipeline:
    """The open pipeline: every deal still being prepared or competed for."""
    window = DayWindow.containing(now, ZoneInfo(settings.briefing_timezone))
    open_ = (Deal.user_id == user.id, Deal.stage.in_(OPEN_STAGES), live(Deal))
    stage_order = case({stage: i for i, stage in enumerate(OPEN_STAGES)}, value=Deal.stage)
    rows = list(
        await session.scalars(
            select(Deal)
            .where(*open_)
            .order_by(
                stage_order, Deal.expected_close_date.asc().nulls_last(), Deal.created_at, Deal.id
            )
            .limit(MAX_PIPELINE_DEALS + 1)
        )
    )
    totals: dict[str, Decimal] = {
        currency: total
        for currency, total in (
            await session.execute(
                select(Deal.currency, func.sum(Deal.expected_value))
                .where(*open_)
                .group_by(Deal.currency)
                .having(func.sum(Deal.expected_value).is_not(None))
                .order_by(Deal.currency)
            )
        ).tuples()
        if total is not None
    }
    return AgentPipeline(
        deals=[
            AgentDeal(
                id=d.id,
                title=d.title,
                stage=d.stage,
                currency=d.currency,
                days_in_stage=window.days_late(d.stage_changed_at),
                expected_value=d.expected_value,
                probability=d.probability,
                expected_close_date=d.expected_close_date,
                contact_name=d.contact_name,
                organization_name=d.organization_name,
            )
            for d in rows[:MAX_PIPELINE_DEALS]
        ],
        totals=totals,
        truncated=True if len(rows) > MAX_PIPELINE_DEALS else None,
    )


def _task(task: Task, window: DayWindow, *, late: bool) -> AgentTask:
    return AgentTask(
        id=task.id,
        title=task.title,
        priority=task.priority,
        due_date=task.due_date,
        days_late=window.days_late(task.due_date) if late and task.due_date else None,
        contact_name=task.contact_name,
        deal_title=task.deal_title,
    )


@router.get("/tasks/today", response_model=AgentTasks, response_model_exclude_none=True)
async def tasks_today(
    now: datetime = Depends(current_time),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_token_user),
) -> AgentTasks:
    """Open tasks that are overdue, and those due today, in the operator's timezone."""
    window = DayWindow.containing(now, ZoneInfo(settings.briefing_timezone))
    queries = briefing_queries(user.id, window)
    overdue = list(await session.scalars(queries.overdue_tasks))
    today = list(await session.scalars(queries.tasks_today))
    return AgentTasks(
        date=window.today,
        timezone=window.tz.key,
        overdue=[_task(t, window, late=True) for t in overdue],
        today=[_task(t, window, late=False) for t in today],
    )
