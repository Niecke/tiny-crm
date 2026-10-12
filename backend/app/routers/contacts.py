from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import DateTime, String, case, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import archived_is, require_archived, require_live, set_archived
from app.audit import AuditEvent, check_version, erase_history, record_update, snapshot
from app.auth import current_active_user
from app.auth.users import User
from app.db import contains, count_rows, get_session
from app.importers.vcard import contact_to_vcard, contacts_to_vcards, import_vcards
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.document import Document, document_contacts
from app.models.interaction import Interaction, interaction_contacts
from app.models.organization import Organization
from app.models.task import Task
from app.schemas.contact import (
    ContactCreate,
    ContactRead,
    ContactSource,
    ContactUpdate,
    FreelancerAnswer,
    LifecycleStatus,
    RelationType,
)
from app.schemas.import_export import VCardImportSummary
from app.schemas.page import Page
from app.schemas.timeline import TimelineItemRead, TimelineItemType
from app.uploads import checked_size

router = APIRouter(prefix="/contacts", tags=["contacts"])


async def _get_owned(session: AsyncSession, contact_id: UUID, user: User) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


async def _check_organization(
    session: AsyncSession, organization_id: UUID | None, user: User
) -> None:
    """Refuse an organization_id that is missing or belongs to someone else.

    Without this the FK would accept any existing id, quietly filing a contact
    under another tenant's company — and leaking that company's name back on
    every read.
    """
    if organization_id is None:
        return
    organization = await session.get(Organization, organization_id)
    if organization is None or organization.user_id != user.id:
        raise HTTPException(status_code=404, detail="Organization not found")


def _reject_orphan_rate(known_day_rate: Decimal | None, rate_currency: str | None) -> None:
    """Refuse half of a rate.

    "800" is not a rate and "EUR" is not a number — the same rule the deals
    router applies to a volume with no unit. Neither half can be read back six
    months later without the other.
    """
    if known_day_rate is not None and rate_currency is None:
        raise HTTPException(
            status_code=422,
            detail="rate_currency is required when a known day rate is given",
        )
    if rate_currency is not None and known_day_rate is None:
        raise HTTPException(
            status_code=422,
            detail="rate_currency is only valid alongside a known day rate",
        )


def _merge_rate_fields(contact: Contact, updates: dict[str, Any]) -> None:
    """Validate the rate pair as it will be *after* this PATCH.

    A PATCH that sets only `known_day_rate` on a contact with no currency has
    to be refused even though the request never mentions a currency, so the
    check runs against the merged row rather than against what was sent.

    Clearing the rate clears the currency with it: a currency alone says
    nothing, and making the caller remember to send both would be a trap rather
    than a rule. Sending a currency explicitly alongside that clear still fails
    — that is a contradiction, not a tidy-up.
    """
    if "known_day_rate" in updates and updates["known_day_rate"] is None:
        updates.setdefault("rate_currency", None)
    _reject_orphan_rate(
        updates.get("known_day_rate", contact.known_day_rate),
        updates.get("rate_currency", contact.rate_currency),
    )


@router.get("/", response_model=Page[ContactRead])
async def list_contacts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    # Two orthogonal questions, so two filters: "how far along are we" and
    # "what is this party to me". Sent together they narrow rather than widen —
    # "partners we have not approached yet" is one request.
    lifecycle_status: LifecycleStatus | None = Query(default=None),
    relation_type: RelationType | None = Query(default=None),
    source: ContactSource | None = Query(default=None),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    # Tri-state, because a bool could not ask for the never-asked ones — and
    # those are the list that produces the next approach.
    works_with_freelancers: FreelancerAnswer | None = Query(default=None),
    # The archive instead of the list, never the two mixed: see app/archive.py.
    archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[ContactRead]:
    q = select(Contact).where(Contact.user_id == user.id, archived_is(Contact, archived))
    if search:
        q = q.where(contains(Contact.name, search))
    # "Everyone at ACME" — the question free-text company could never answer.
    if organization_id is not None:
        q = q.where(Contact.organization_id == organization_id)
    if lifecycle_status is not None:
        q = q.where(Contact.lifecycle_status == lifecycle_status)
    if relation_type is not None:
        q = q.where(Contact.relation_type == relation_type)
    if source is not None:
        q = q.where(Contact.source == source)
    if country is not None:
        # Stored upper-cased by the schema, so match that rather than trusting
        # however the caller happened to type it.
        q = q.where(Contact.country == country.upper())
    if works_with_freelancers is not None:
        if works_with_freelancers == "unknown":
            q = q.where(Contact.works_with_freelancers.is_(None))
        else:
            q = q.where(Contact.works_with_freelancers.is_(works_with_freelancers == "yes"))

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


MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB


@router.get(
    "/vcard",
    response_class=Response,
    responses={
        200: {
            "content": {"text/vcard": {"schema": {"type": "string"}}},
            "description": "Export all contacts in vCard format.",
        }
    },
)
async def export_vcards(
    archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Response:
    """Export all active (or archived) contacts as a multi-vCard .vcf file."""
    q = (
        select(Contact)
        .where(Contact.user_id == user.id, archived_is(Contact, archived))
        .order_by(Contact.name.asc(), Contact.id.asc())
    )
    result = await session.execute(q)
    contacts = result.scalars().all()
    vcard_text = contacts_to_vcards(contacts)
    return Response(
        content=vcard_text,
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contacts.vcf"'},
    )


@router.post("/import/vcard", response_model=VCardImportSummary)
async def import_contacts_vcard(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> VCardImportSummary:
    """Import contacts from a vCard (.vcf) file."""
    checked_size(file, MAX_IMPORT_BYTES)
    try:
        content_bytes = await file.read()
        text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=422, detail="File must be valid UTF-8 encoded vCard."
        ) from None

    return await import_vcards(session, user, text)


@router.get(
    "/{contact_id}/vcard",
    response_class=Response,
    responses={
        200: {
            "content": {"text/vcard": {"schema": {"type": "string"}}},
            "description": "Export single contact in vCard format.",
        }
    },
)
async def export_contact_vcard(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Response:
    """Export a single contact as a .vcf file."""
    contact = await _get_owned(session, contact_id, user)
    vcard_text = contact_to_vcard(contact)
    # Headers are Latin-1, so the plain filename is ASCII only — str.isalnum()
    # alone would let "Jiří" through and fail the response. The real name
    # travels in filename*, as it does for a document download.
    safe_name = "".join(
        c for c in contact.name if c.isascii() and (c.isalnum() or c in ("-", "_", " "))
    ).strip()
    safe_name = safe_name.replace(" ", "_") or "contact"
    encoded_filename = quote(f"{contact.name.strip()}.vcf", safe="")
    return Response(
        content=vcard_text,
        media_type="text/vcard; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{safe_name}.vcf\"; filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    # Archived or not: the interactions and deals that name an archived contact
    # still link here, and a link that answered 404 would be the anonymised
    # history archiving exists to prevent.
    return await _get_owned(session, contact_id, user)


@router.get("/{contact_id}/timeline", response_model=Page[TimelineItemRead])
async def get_contact_timeline(
    contact_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    types: list[TimelineItemType] | None = Query(default=None),
    archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[TimelineItemRead]:
    """The contact's unified timeline, newest first.

    Merges interactions, tasks, deals, documents and contact field changes into
    a single reverse-chronological feed.
    """
    await _get_owned(session, contact_id, user)

    parsed_types = set(types) if types else set()

    subqueries = []

    if not parsed_types or "interaction" in parsed_types:
        q_interactions = (
            select(
                Interaction.id.label("id"),
                literal("interaction").label("item_type"),
                Interaction.occurred_at.label("timestamp"),
                Interaction.subject.label("title"),
                Interaction.notes.label("description"),
                func.jsonb_build_object(
                    "kind",
                    Interaction.kind,
                    "done",
                    Interaction.done,
                    "duration_minutes",
                    Interaction.duration_minutes,
                    "tags",
                    Interaction.tags,
                ).label("metadata"),
            )
            .join(interaction_contacts, interaction_contacts.c.interaction_id == Interaction.id)
            .where(
                interaction_contacts.c.contact_id == contact_id,
                Interaction.user_id == user.id,
                archived_is(Interaction, archived),
            )
        )
        subqueries.append(q_interactions)

    if not parsed_types or "task" in parsed_types:
        q_tasks = select(
            Task.id.label("id"),
            literal("task").label("item_type"),
            func.coalesce(Task.completed_at, Task.due_date, Task.created).label("timestamp"),
            Task.title.label("title"),
            Task.description.label("description"),
            func.jsonb_build_object(
                "done",
                Task.done,
                "priority",
                Task.priority,
                "due_date",
                Task.due_date,
                "completed_at",
                Task.completed_at,
                "tags",
                Task.tags,
            ).label("metadata"),
        ).where(
            Task.contact_id == contact_id,
            Task.user_id == user.id,
            archived_is(Task, archived),
        )
        subqueries.append(q_tasks)

    if not parsed_types or "deal" in parsed_types:
        q_deals = select(
            Deal.id.label("id"),
            literal("deal").label("item_type"),
            func.coalesce(Deal.stage_changed_at, Deal.created_at).label("timestamp"),
            Deal.title.label("title"),
            Deal.notes.label("description"),
            func.jsonb_build_object(
                "stage",
                Deal.stage,
                "expected_value",
                Deal.expected_value,
                "currency",
                Deal.currency,
                "probability",
                Deal.probability,
            ).label("metadata"),
        ).where(
            Deal.contact_id == contact_id,
            Deal.user_id == user.id,
            archived_is(Deal, archived),
        )
        subqueries.append(q_deals)

    if not parsed_types or "document" in parsed_types:
        q_documents = (
            select(
                Document.id.label("id"),
                literal("document").label("item_type"),
                cast(Document.created_at, DateTime(timezone=True)).label("timestamp"),
                Document.title.label("title"),
                Document.description.label("description"),
                func.jsonb_build_object(
                    "format",
                    Document.format,
                    "size",
                    Document.size,
                    "preview_key",
                    Document.preview_key,
                    "tags",
                    Document.tags,
                ).label("metadata"),
            )
            .join(document_contacts, document_contacts.c.document_id == Document.id)
            .where(
                document_contacts.c.contact_id == contact_id,
                Document.user_id == user.id,
                archived_is(Document, archived),
            )
        )
        subqueries.append(q_documents)

    if not parsed_types or "change" in parsed_types:
        q_changes = select(
            AuditEvent.id.label("id"),
            literal("change").label("item_type"),
            AuditEvent.created_at.label("timestamp"),
            case(
                (AuditEvent.action == "update", "Contact updated"),
                (AuditEvent.action == "archive", "Contact archived"),
                (AuditEvent.action == "restore", "Contact restored"),
                else_=AuditEvent.action,
            ).label("title"),
            cast(None, String).label("description"),
            func.jsonb_build_object(
                "action",
                AuditEvent.action,
                "actor_id",
                AuditEvent.actor_id,
                "changes",
                AuditEvent.changes,
            ).label("metadata"),
        ).where(
            AuditEvent.entity_type == "contact",
            AuditEvent.entity_id == contact_id,
            AuditEvent.user_id == user.id,
        )
        subqueries.append(q_changes)

    if not subqueries:
        return Page[TimelineItemRead](items=[], total=0, skip=skip, limit=limit)

    u = union_all(*subqueries).subquery("timeline")
    count_q = select(func.count()).select_from(u)
    total = await session.scalar(count_q) or 0

    final_q = select(u).order_by(u.c.timestamp.desc(), u.c.id.desc()).offset(skip).limit(limit)
    result = await session.execute(final_q)
    items = [
        TimelineItemRead(
            id=row.id,
            item_type=row.item_type,
            timestamp=row.timestamp,
            title=row.title,
            description=row.description,
            metadata=row.metadata or {},
        )
        for row in result.all()
    ]
    return Page[TimelineItemRead](items=items, total=total, skip=skip, limit=limit)


@router.post("/", response_model=ContactRead, status_code=201)
async def create_contact(
    body: ContactCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    await _check_organization(session, body.organization_id, user)
    _reject_orphan_rate(body.known_day_rate, body.rate_currency)
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
    contact = await _get_owned(session, contact_id, user)
    require_live(contact, "Contact")
    updates = body.model_dump(exclude_unset=True)
    check_version(contact, updates.pop("version", None), "Contact")
    if "organization_id" in updates:
        await _check_organization(session, updates["organization_id"], user)
    if "known_day_rate" in updates or "rate_currency" in updates:
        _merge_rate_fields(contact, updates)
    before = snapshot(contact)
    # exclude_unset=True — only update fields the caller actually sent
    for field, value in updates.items():
        setattr(contact, field, value)
    record_update(session, user, contact, before)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.post("/{contact_id}/archive", response_model=ContactRead)
async def archive_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    """Put the contact away, keeping everything that points at them.

    The interactions, deals and tasks that name this contact go on naming them.
    That is the difference from DELETE, which leaves each of those pointing at
    nobody.
    """
    contact = await _get_owned(session, contact_id, user)
    await set_archived(session, contact, True, user)
    return contact


@router.post("/{contact_id}/restore", response_model=ContactRead)
async def restore_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Contact:
    """Bring an archived contact back, exactly as it was put away."""
    contact = await _get_owned(session, contact_id, user)
    await set_archived(session, contact, False, user)
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    """Erase the contact for good. Only once it has been archived.

    This is the erasure, not the tidy-up (#143): the row goes, and every task,
    deal and interaction that named this person stops naming anyone.
    """
    contact = await _get_owned(session, contact_id, user)
    require_archived(contact, "Contact")
    await erase_history(session, contact)
    await session.delete(contact)
    await session.commit()
