from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.models.contact import Contact
from app.models.interaction import Interaction, interaction_contacts
from app.schemas.interaction import (
    InteractionCreate,
    InteractionKind,
    InteractionRead,
    InteractionUpdate,
)
from app.schemas.page import Page

router = APIRouter(prefix="/interactions", tags=["interactions"])


def _to_read(i: Interaction) -> InteractionRead:
    return InteractionRead(
        id=i.id,
        kind=cast(InteractionKind, i.kind),
        subject=i.subject,
        notes=i.notes,
        occurred_at=i.occurred_at,
        duration_minutes=i.duration_minutes,
        done=i.done,
        tags=i.tags,
        contact_ids=[c.id for c in i.contacts],
        created_at=i.created_at,
        updated_at=i.updated_at,
    )


async def _load_contacts(session: AsyncSession, ids: list[UUID], user_id: UUID) -> list[Contact]:
    """Fetch the given contact ids belonging to user_id. 404 on any miss."""
    if not ids:
        return []
    result = await session.execute(
        select(Contact).where(Contact.id.in_(ids), Contact.user_id == user_id)
    )
    found = list(result.scalars().all())
    if len(found) != len(set(ids)):
        raise HTTPException(status_code=404, detail="Unknown Contact id in link list")
    return found


@router.get("/", response_model=Page[InteractionRead])
async def list_interactions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = None,
    contact_id: UUID | None = None,
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
    if contact_id:
        query = query.join(
            interaction_contacts,
            interaction_contacts.c.interaction_id == Interaction.id,
        ).where(interaction_contacts.c.contact_id == contact_id)
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
        items=[_to_read(i) for i in result.scalars().all()],
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
    return _to_read(interaction)


@router.post("/", response_model=InteractionRead, status_code=201)
async def create_interaction(
    body: InteractionCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> InteractionRead:
    data = body.model_dump(exclude={"contact_ids"})
    interaction = Interaction(**data, user_id=user.id)
    interaction.contacts = await _load_contacts(session, body.contact_ids, user.id)
    session.add(interaction)
    await session.commit()
    await session.refresh(interaction)
    return _to_read(interaction)


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
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "contact_ids":
            interaction.contacts = await _load_contacts(session, value, user.id)
        else:
            setattr(interaction, field, value)
    await session.commit()
    await session.refresh(interaction)
    return _to_read(interaction)


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
