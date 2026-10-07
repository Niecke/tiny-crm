from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Label, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import archived_is, live, require_archived, require_live, set_archived
from app.auth import current_active_user
from app.auth.users import User
from app.db import contains, count_rows, get_session
from app.models.contact import Contact
from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.schemas.page import Page

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _contact_count_column() -> Label[int]:
    """Contacts per organization, as a correlated subquery.

    One extra column on the list query instead of a request per row — the list
    is the screen that answers "who is this company, and how many people do we
    know there?". Archived contacts are not counted: the number has to match
    the list of people it links to.
    """
    return (
        select(func.count(Contact.id))
        .where(Contact.organization_id == Organization.id, live(Contact))
        .correlate(Organization)
        .scalar_subquery()
        .label("contact_count")
    )


async def _count_contacts(session: AsyncSession, organization_id: UUID) -> int:
    total = await session.scalar(
        select(func.count(Contact.id)).where(
            Contact.organization_id == organization_id, live(Contact)
        )
    )
    return total or 0


def _to_read(organization: Organization, contact_count: int) -> OrganizationRead:
    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        domain=organization.domain,
        email=organization.email,
        phone=organization.phone,
        address=organization.address,
        industry=organization.industry,
        notes=organization.notes,
        contact_count=contact_count,
        archived_at=organization.archived_at,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


async def _get_owned(session: AsyncSession, organization_id: UUID, user: User) -> Organization:
    organization = await session.get(Organization, organization_id)
    if organization is None or organization.user_id != user.id:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.get("/", response_model=Page[OrganizationRead])
async def list_organizations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[OrganizationRead]:
    q = select(Organization).where(
        Organization.user_id == user.id, archived_is(Organization, archived)
    )
    if search:
        # Domain as well as name: "acme.example" from an email signature is
        # often all the operator has to go on.
        q = q.where(
            or_(
                contains(Organization.name, search),
                contains(Organization.domain, search),
            )
        )
    total = await count_rows(session, q)
    # Name is not unique, so id is the tiebreaker that keeps paging stable.
    result = await session.execute(
        q.add_columns(_contact_count_column())
        .order_by(Organization.name.asc(), Organization.id.asc())
        .offset(skip)
        .limit(limit)
    )
    return Page[OrganizationRead](
        items=[_to_read(org, count) for org, count in result.all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> OrganizationRead:
    organization = await _get_owned(session, organization_id, user)
    return _to_read(organization, await _count_contacts(session, organization.id))


@router.post("/", response_model=OrganizationRead, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> OrganizationRead:
    organization = Organization(**body.model_dump(), user_id=user.id)
    session.add(organization)
    await session.commit()
    await session.refresh(organization)
    return _to_read(organization, 0)


@router.patch("/{organization_id}", response_model=OrganizationRead)
async def update_organization(
    organization_id: UUID,
    body: OrganizationUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> OrganizationRead:
    organization = await _get_owned(session, organization_id, user)
    require_live(organization, "Organization")
    # exclude_unset=True — only update fields the caller actually sent
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(organization, field, value)
    await session.commit()
    await session.refresh(organization)
    return _to_read(organization, await _count_contacts(session, organization.id))


@router.post("/{organization_id}/archive", response_model=OrganizationRead)
async def archive_organization(
    organization_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> OrganizationRead:
    """Put the company away. Its people stay where they are, still filed under it.

    Nothing cascades: whether the contacts go too is a separate decision, and
    making it silently is the opposite of recoverable.
    """
    organization = await _get_owned(session, organization_id, user)
    await set_archived(session, organization, True)
    return _to_read(organization, await _count_contacts(session, organization.id))


@router.post("/{organization_id}/restore", response_model=OrganizationRead)
async def restore_organization(
    organization_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> OrganizationRead:
    """Bring an archived company back, exactly as it was put away."""
    organization = await _get_owned(session, organization_id, user)
    await set_archived(session, organization, False)
    return _to_read(organization, await _count_contacts(session, organization.id))


@router.delete("/{organization_id}", status_code=204)
async def delete_organization(
    organization_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    """Erase the company for good. Only once it has been archived.

    Deleting a company keeps its people: their organization_id becomes NULL.
    """
    organization = await _get_owned(session, organization_id, user)
    require_archived(organization, "Organization")
    await session.delete(organization)
    await session.commit()
