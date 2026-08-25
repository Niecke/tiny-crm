from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.schemas.page import Page

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/", response_model=Page[ContactRead])
async def list_contacts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[ContactRead]:
    q = select(Contact).where(Contact.user_id == user.id)
    if search:
        q = q.where(Contact.name.ilike(f"%{search}%"))
    total = await count_rows(session, q)
    # Paging without a total order lets rows repeat or vanish between pages,
    # so every list sorts by something unique-enough plus id as a tiebreaker.
    result = await session.execute(
        q.order_by(Contact.name.asc(), Contact.id.asc()).offset(skip).limit(limit)
    )
    return Page[ContactRead](
        items=[ContactRead.model_validate(c) for c in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("/", response_model=ContactRead, status_code=201)
async def create_contact(
    body: ContactCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    contact = Contact(**body.model_dump(), user_id=user.id)
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: UUID,
    body: ContactUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    # exclude_unset=True — only update fields the caller actually sent
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await session.delete(contact)
    await session.commit()
