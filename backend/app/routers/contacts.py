from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.db import get_session
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(
    prefix="/contacts", tags=["contacts"], dependencies=[Depends(current_active_user)]
)


@router.get("/", response_model=list[ContactRead])
async def list_contacts(
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[Contact]:
    result = await session.execute(select(Contact).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.post("/", response_model=ContactRead, status_code=201)
async def create_contact(
    body: ContactCreate,
    session: AsyncSession = Depends(get_session),
) -> Contact:
    contact = Contact(**body.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: int,
    body: ContactUpdate,
    session: AsyncSession = Depends(get_session),
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    # exclude_unset=True — only update fields the caller actually sent
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await session.delete(contact)
    await session.commit()
