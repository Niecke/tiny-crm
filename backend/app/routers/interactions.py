from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.links import filter_by_link, load_scoped
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.interaction import (
    Interaction,
    interaction_contacts,
    interaction_deals,
    interaction_organizations,
    interaction_projects,
)
from app.models.organization import Organization
from app.models.project import Project
from app.schemas.interaction import (
    InteractionCreate,
    InteractionKind,
    InteractionRead,
    InteractionUpdate,
)
from app.schemas.page import Page

router = APIRouter(prefix="/interactions", tags=["interactions"])

# Everything an interaction can be about: the API field, the relationship it
# fills, the model its ids are checked against, and the join table plus its
# column for the list filter.
LINKS = (
    ("contact_ids", "contacts", Contact, interaction_contacts, "contact_id"),
    (
        "organization_ids",
        "organizations",
        Organization,
        interaction_organizations,
        "organization_id",
    ),
    ("deal_ids", "deals", Deal, interaction_deals, "deal_id"),
    ("project_ids", "projects", Project, interaction_projects, "project_id"),
)


async def _apply_links(
    session: AsyncSession, interaction: Interaction, values: dict[str, object], user_id: UUID
) -> None:
    """Replace whichever link lists the caller sent, leaving the rest alone."""
    for field, attribute, model, _table, _column in LINKS:
        if field not in values:
            continue
        ids = cast(list[UUID], values[field])
        setattr(interaction, attribute, await load_scoped(session, model, ids, user_id))


@router.get("/", response_model=Page[InteractionRead])
async def list_interactions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = None,
    contact_id: UUID | None = None,
    # "Every call about this deal" — with contacts as the only link, there was
    # no way to ask.
    organization_id: UUID | None = None,
    deal_id: UUID | None = None,
    project_id: UUID | None = None,
    kind: InteractionKind | None = None,
    upcoming: bool | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[InteractionRead]:
    """List interactions, newest first.

    `upcoming=true` returns only planned (future) entries, oldest first so the
    next appointment comes up top; `upcoming=false` returns only the past log.
    """
    query = select(Interaction).where(Interaction.user_id == user.id)
    if search:
        query = query.where(Interaction.subject.ilike(f"%{search}%"))
    if kind:
        query = query.where(Interaction.kind == kind)
    for target_id, (_field, _attr, _model, table, column) in zip(
        (contact_id, organization_id, deal_id, project_id), LINKS, strict=True
    ):
        if target_id is not None:
            query = filter_by_link(query, table, "interaction_id", column, target_id)
    now = datetime.now(UTC)
    if upcoming is True:
        query = query.where(Interaction.occurred_at >= now)
    elif upcoming is False:
        query = query.where(Interaction.occurred_at < now)

    total = await count_rows(session, query)

    # Ascending for planned entries so the next appointment comes up top,
    # descending everywhere else so the newest log entry does. id breaks ties,
    # otherwise rows can repeat or vanish between pages.
    if upcoming is True:
        query = query.order_by(Interaction.occurred_at.asc(), Interaction.id.asc())
    else:
        query = query.order_by(Interaction.occurred_at.desc(), Interaction.id.asc())

    result = await session.execute(query.offset(skip).limit(limit))
    return Page[InteractionRead](
        items=[InteractionRead.model_validate(i) for i in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{interaction_id}", response_model=InteractionRead)
async def get_interaction(
    interaction_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> InteractionRead:
    interaction = await session.get(Interaction, interaction_id)
    if interaction is None or interaction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return InteractionRead.model_validate(interaction)


@router.post("/", response_model=InteractionRead, status_code=201)
async def create_interaction(
    body: InteractionCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> InteractionRead:
    link_fields = {field for field, *_ in LINKS}
    interaction = Interaction(**body.model_dump(exclude=link_fields), user_id=user.id)
    await _apply_links(session, interaction, body.model_dump(), user.id)
    session.add(interaction)
    await session.commit()
    await session.refresh(interaction)
    return InteractionRead.model_validate(interaction)


@router.patch("/{interaction_id}", response_model=InteractionRead)
async def update_interaction(
    interaction_id: UUID,
    body: InteractionUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> InteractionRead:
    interaction = await session.get(Interaction, interaction_id)
    if interaction is None or interaction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Interaction not found")
    updates = body.model_dump(exclude_unset=True)
    await _apply_links(session, interaction, updates, user.id)
    for field, value in updates.items():
        # The link lists are handled above; setattr would assign raw ids.
        if not field.endswith("_ids"):
            setattr(interaction, field, value)
    await session.commit()
    await session.refresh(interaction)
    return InteractionRead.model_validate(interaction)


@router.delete("/{interaction_id}", status_code=204)
async def delete_interaction(
    interaction_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    interaction = await session.get(Interaction, interaction_id)
    if interaction is None or interaction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Interaction not found")
    await session.delete(interaction)
    await session.commit()
