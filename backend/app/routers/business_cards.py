"""Business card scanning (#262): photos of a card in, a contact and its company out.

Two steps, so nothing is filed that the operator has not seen:

1. POST /business-cards/scan reads the photos and returns a draft, plus the
   company already on file that the card most likely belongs to. Nothing is
   written.
2. POST /business-cards/import files the corrected draft — the company, if it
   is new, and the contact under it — in one transaction, so a failure never
   leaves a company with nobody at it.
"""

import re
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import live
from app.auth import current_active_user
from app.auth.users import User
from app.business_cards import (
    MAX_IMAGE_BYTES,
    CardImage,
    CardReader,
    CardReadError,
    CardReading,
    get_card_reader,
    sniff_image_type,
)
from app.db import get_session
from app.models.contact import Contact
from app.models.organization import Organization
from app.routers.contacts import _check_organization, _reject_orphan_rate
from app.schemas.business_card import (
    BusinessCardImport,
    BusinessCardScan,
    CardContactDraft,
    CardOrganizationDraft,
    OrganizationMatch,
)
from app.schemas.contact import ContactRead

router = APIRouter(prefix="/business-cards", tags=["business-cards"])

# Mailbox providers: an address there says nothing about the company.
_FREEMAIL = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "proton.me",
        "protonmail.com",
        "gmx.at",
        "gmx.de",
        "gmx.net",
        "web.de",
        "t-online.de",
        "aon.at",
        "a1.net",
        "mail.com",
    }
)


async def _read_image(file: UploadFile, side: str) -> CardImage:
    size = file.size
    if size is not None and size > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"The {side} photo is larger than 5 MB")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"The {side} photo is larger than 5 MB")
    media_type = sniff_image_type(data)
    if media_type is None:
        raise HTTPException(
            status_code=415, detail=f"The {side} photo must be a JPEG, PNG, GIF or WebP image"
        )
    return CardImage(data, media_type)


def _clean(value: str | None) -> str | None:
    """Trimmed, and None rather than an empty string."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalise_domain(value: str | None) -> str | None:
    """`https://www.Acme.example/team` → `acme.example`. None for anything that
    is not a host name."""
    value = _clean(value)
    if value is None:
        return None
    host = urlsplit(value if "://" in value else f"//{value}").hostname
    if not host or "." not in host:
        return None
    host = host.lower().removeprefix("www.")
    return host


def company_domain(reading: CardReading) -> str | None:
    """The company's domain: printed as such, else the website's, else the
    email's — unless that is a mailbox provider's."""
    for candidate in (reading.organization_domain, reading.website):
        domain = normalise_domain(candidate)
        if domain:
            return domain
    for address in (reading.email, reading.organization_email):
        address = _clean(address)
        if address and "@" in address:
            domain = normalise_domain(address.rsplit("@", 1)[1])
            if domain and domain not in _FREEMAIL:
                return domain
    return None


def _country(value: str | None) -> str | None:
    value = _clean(value)
    return value.upper() if value and re.fullmatch(r"[A-Za-z]{2}", value) else None


def to_drafts(reading: CardReading) -> tuple[CardContactDraft, CardOrganizationDraft | None]:
    contact = CardContactDraft(
        name=_clean(reading.name),
        job_title=_clean(reading.job_title),
        email=_clean(reading.email),
        email_secondary=_clean(reading.email_secondary),
        phone=_clean(reading.phone),
        phone_secondary=_clean(reading.phone_secondary),
        website=_clean(reading.website),
        street=_clean(reading.street),
        postal_code=_clean(reading.postal_code),
        city=_clean(reading.city),
        country=_country(reading.country),
        notes=_clean(reading.notes),
    )
    name = _clean(reading.organization_name)
    if name is None:
        return contact, None
    # A card prints one address, and it is the office's: the company keeps it
    # as one line, the contact in parts.
    place = " ".join(p for p in (contact.postal_code, contact.city) if p)
    address = ", ".join(p for p in (contact.street, place, contact.country) if p) or None
    organization = CardOrganizationDraft(
        name=name,
        domain=company_domain(reading),
        email=_clean(reading.organization_email),
        phone=_clean(reading.organization_phone),
        address=address,
    )
    return contact, organization


# The host part of a domain stored as typed — "acme.example",
# "www.acme.example", "https://www.Acme.example/team?ref=card" — in SQL, the
# same reduction normalise_domain() makes on the card's side.
_HOST_PATTERN = r"^([a-z][a-z0-9+.-]*://)?(www\.)?([^/?#:]*).*$"


def _stored_host() -> ColumnElement[str]:
    return func.regexp_replace(func.lower(func.trim(Organization.domain)), _HOST_PATTERN, r"\3")


async def find_organization(
    session: AsyncSession, user: User, draft: CardOrganizationDraft
) -> OrganizationMatch | None:
    """The live company on file this card belongs to: same domain first, then
    the same name ignoring case."""
    owned = select(Organization).where(Organization.user_id == user.id, live(Organization))
    if draft.domain:
        found = await session.scalar(
            owned.where(_stored_host() == draft.domain)
            .order_by(Organization.created_at.asc())
            .limit(1)
        )
        if found is not None:
            return OrganizationMatch(id=found.id, name=found.name, matched_on="domain")
    found = await session.scalar(
        owned.where(func.lower(func.trim(Organization.name)) == draft.name.lower())
        .order_by(Organization.created_at.asc())
        .limit(1)
    )
    if found is not None:
        return OrganizationMatch(id=found.id, name=found.name, matched_on="name")
    return None


@router.post("/scan", response_model=BusinessCardScan)
async def scan_business_card(
    front: Annotated[UploadFile, File(description="Photo of the card's front")],
    back: Annotated[UploadFile | None, File(description="Photo of the card's back")] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
    reader: CardReader | None = Depends(get_card_reader),
) -> BusinessCardScan:
    """Read a card from photos of its front and, if it has one, its back.

    Returns a draft to correct, never a filed record. The photos are not kept.
    """
    if reader is None:
        raise HTTPException(
            status_code=503,
            detail="Business card scanning is not set up: ANTHROPIC_API_KEY is not configured",
        )
    images = [await _read_image(front, "front")]
    if back is not None:
        images.append(await _read_image(back, "back"))
    try:
        read = await reader.read(images)
    except CardReadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None

    contact, organization = to_drafts(read.reading)
    if contact.name is None and organization is None:
        raise HTTPException(
            status_code=422,
            detail="No name or company could be read from these photos — try a sharper photo",
        )
    match = await find_organization(session, user, organization) if organization else None
    return BusinessCardScan(
        contact=contact, organization=organization, match=match, usage=read.usage
    )


@router.post("/import", response_model=ContactRead, status_code=201)
async def import_business_card(
    body: BusinessCardImport,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    """File a checked card: a new company if one is given, and the contact under it."""
    if body.organization is not None and body.contact.organization_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Send either a new organization or contact.organization_id, not both",
        )
    await _check_organization(session, body.contact.organization_id, user)
    _reject_orphan_rate(body.contact.known_day_rate, body.contact.rate_currency)

    values = body.contact.model_dump()
    if body.organization is not None:
        organization = Organization(**body.organization.model_dump(), user_id=user.id)
        session.add(organization)
        await session.flush()
        values["organization_id"] = organization.id
    contact = Contact(**values, user_id=user.id)
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact
