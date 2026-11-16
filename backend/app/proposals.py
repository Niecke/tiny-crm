"""What the agent endpoint and the review endpoints share (#321).

An agent stages a change as an `AgentProposal`; the operator approves it, and
only then does it reach the CRM. Both sides need the same few things — check a
payload against the entity's own schema, find the target, resolve names for
display, apply the change — so they live here, and neither router imports the
other. That keeps the boundary from #320 intact: app/routers/agent.py never
sees a session credential, and app/routers/proposals.py never sees a token.

Applying goes through `apply_create` / `apply_update` in the session routers
and `mark_archived`: the code the web client itself runs, with the same
validation, history entries, stage events and recurrence. They do not commit,
so the caller can mark the proposal approved in the same transaction.
"""

import json
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import mark_archived
from app.auth.users import User
from app.models import Contact, Deal, Interaction, Organization, Project, Task
from app.models.proposal import AgentProposal
from app.routers import contacts, deals, interactions, organizations, tasks
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.schemas.deal import DealCreate, DealRead, DealUpdate
from app.schemas.interaction import InteractionCreate, InteractionRead, InteractionUpdate
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.schemas.proposal import EntityType, ProposalAction
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

# entity type -> (Create, Update, Read) schemas.
SCHEMAS: dict[EntityType, tuple[type[BaseModel], type[BaseModel], type[BaseModel]]] = {
    "contact": (ContactCreate, ContactUpdate, ContactRead),
    "organization": (OrganizationCreate, OrganizationUpdate, OrganizationRead),
    "deal": (DealCreate, DealUpdate, DealRead),
    "task": (TaskCreate, TaskUpdate, TaskRead),
    "interaction": (InteractionCreate, InteractionUpdate, InteractionRead),
}

# entity type -> (ORM class, the attribute that names a row, label for errors).
MODELS: dict[EntityType, tuple[Any, str, str]] = {
    "contact": (Contact, "name", "Contact"),
    "organization": (Organization, "name", "Organization"),
    "deal": (Deal, "title", "Deal"),
    "task": (Task, "title", "Task"),
    "interaction": (Interaction, "subject", "Interaction"),
}

# Payload fields that hold the id of another record, and what they point at.
# `*_id` holds one id, `*_ids` a list.
_REFERENCE_MODELS: dict[str, Any] = {
    "organization": Organization,
    "contact": Contact,
    "deal": Deal,
    "interaction": Interaction,
    "project": Project,
}
_REFERENCE_LABELS = {
    Organization: "name",
    Contact: "name",
    Deal: "title",
    Interaction: "subject",
    Project: "name",
}


def _reference_model(field: str) -> Any | None:
    for suffix in ("_ids", "_id"):
        if field.endswith(suffix):
            return _REFERENCE_MODELS.get(field.removesuffix(suffix))
    return None


def _reference_ids(values: dict[str, Any]) -> dict[Any, set[UUID]]:
    """Every id in `values` that names another record, grouped by model."""
    found: dict[Any, set[UUID]] = {}
    for field, value in values.items():
        model = _reference_model(field)
        if model is None or value is None:
            continue
        raw = value if isinstance(value, list) else [value]
        for item in raw:
            try:
                found.setdefault(model, set()).add(UUID(str(item)))
            except ValueError:
                continue
    return found


def validate_payload(
    entity_type: EntityType, action: ProposalAction, payload: dict[str, Any]
) -> dict[str, Any]:
    """The payload, checked against the entity's own schema and normalised.

    The result is what gets stored: JSON-safe and holding only the fields that
    were sent, so approving it later means exactly what the agent asked for.
    """
    if action == "archive":
        if payload:
            raise HTTPException(status_code=422, detail="An archive takes no payload")
        return {}
    if "version" in payload:
        raise HTTPException(
            status_code=422,
            detail="version cannot be proposed; it is checked when the change is approved",
        )
    create_schema, update_schema, _read = SCHEMAS[entity_type]
    if action == "update" and not payload:
        raise HTTPException(status_code=422, detail="An update needs at least one field")
    schema = create_schema if action == "create" else update_schema
    try:
        model = schema.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=json.loads(exc.json(include_url=False, include_context=False))
        ) from exc
    return model.model_dump(mode="json", exclude_unset=True)


async def load_target(
    session: AsyncSession, entity_type: EntityType, target_id: UUID, user: User
) -> Any:
    """The record, or 404 — whether it is missing or someone else's."""
    model, _attr, label = MODELS[entity_type]
    row = await session.get(model, target_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return row


def entity_label(entity_type: EntityType) -> str:
    """ "Contact", "Deal"… — how errors name the kind of record."""
    return MODELS[entity_type][2]


def label_of(entity_type: EntityType, row: Any) -> str:
    return str(getattr(row, MODELS[entity_type][1]))


async def check_references(session: AsyncSession, payload: dict[str, Any], user: User) -> None:
    """404 for any id in the payload that is missing or belongs to someone else.

    Run at submission so another tenant's id is never stored, and so the
    operator is never shown a name it should not see. The routers check again
    on approval, since things change in between.
    """
    for field, value in payload.items():
        model = _reference_model(field)
        if model is None or value is None:
            continue
        ids = {UUID(str(item)) for item in (value if isinstance(value, list) else [value])}
        if not ids:
            continue
        rows = await session.execute(
            select(model.id).where(model.id.in_(ids), model.user_id == user.id)
        )
        if len(set(rows.scalars().all())) != len(ids):
            raise HTTPException(status_code=404, detail=f"Unknown id in {field}")


async def apply(
    session: AsyncSession,
    proposal: AgentProposal,
    payload: dict[str, Any],
    user: User,
    version: int | None,
) -> UUID:
    """Make the change, without committing. Returns the id of the record.

    Errors (422, 404, 409) raise from the routers' own checks, before anything
    is committed, so the proposal simply stays pending.
    """
    entity_type = cast(EntityType, proposal.entity_type)
    create_schema, update_schema, _read = SCHEMAS[entity_type]
    if proposal.action == "create":
        body = create_schema.model_validate(payload)
        created: Any
        match entity_type:
            case "contact":
                created = await contacts.apply_create(session, cast(ContactCreate, body), user)
            case "organization":
                created = await organizations.apply_create(
                    session, cast(OrganizationCreate, body), user
                )
            case "deal":
                created = await deals.apply_create(session, cast(DealCreate, body), user)
            case "task":
                created = await tasks.apply_create(session, cast(TaskCreate, body), user)
            case "interaction":
                created = await interactions.apply_create(
                    session, cast(InteractionCreate, body), user
                )
        return cast(UUID, created.id)

    target_id = proposal.target_id
    if target_id is None:
        raise HTTPException(status_code=409, detail="This proposal has no target")
    if proposal.action == "archive":
        row = await load_target(session, entity_type, target_id, user)
        mark_archived(session, row, True, user)
        return target_id

    update = update_schema.model_validate({**payload, "version": version})
    match entity_type:
        case "contact":
            await contacts.apply_update(session, target_id, cast(ContactUpdate, update), user)
        case "organization":
            await organizations.apply_update(
                session, target_id, cast(OrganizationUpdate, update), user
            )
        case "deal":
            await deals.apply_update(session, target_id, cast(DealUpdate, update), user)
        case "task":
            await tasks.apply_update(session, target_id, cast(TaskUpdate, update), user)
        case "interaction":
            await interactions.apply_update(
                session, target_id, cast(InteractionUpdate, update), user
            )
    return target_id


async def current_values(
    session: AsyncSession, proposals: list[AgentProposal]
) -> dict[UUID, tuple[str, dict[str, Any]]]:
    """For updates and archives: proposal id → (target label, its present values).

    An update gets the present value of each proposed field plus `version`, so
    the card can show Current | Proposed and approve against that version. An
    archive gets `archived_at`. One query per entity type, not per proposal.
    """
    wanted: dict[EntityType, set[UUID]] = {}
    for proposal in proposals:
        if proposal.action != "create" and proposal.target_id is not None:
            wanted.setdefault(cast(EntityType, proposal.entity_type), set()).add(proposal.target_id)
    rows: dict[tuple[str, UUID], dict[str, Any]] = {}
    labels: dict[tuple[str, UUID], str] = {}
    for entity_type, ids in wanted.items():
        model, _attr, _label = MODELS[entity_type]
        read_schema = SCHEMAS[entity_type][2]
        found = await session.scalars(select(model).where(model.id.in_(ids)))
        for row in found:
            rows[(entity_type, row.id)] = read_schema.model_validate(
                row, from_attributes=True
            ).model_dump(mode="json")
            labels[(entity_type, row.id)] = label_of(entity_type, row)

    result: dict[UUID, tuple[str, dict[str, Any]]] = {}
    for proposal in proposals:
        key = (proposal.entity_type, proposal.target_id)
        if proposal.target_id is None or key not in rows:
            continue
        row_values = rows[key]
        if proposal.action == "archive":
            keep = {"archived_at": row_values.get("archived_at")}
        else:
            keep = {k: row_values.get(k) for k in proposal.proposed_payload}
            keep["version"] = row_values.get("version")
        result[proposal.id] = (labels[key], keep)
    return result


async def reference_labels(
    session: AsyncSession,
    proposals: list[AgentProposal],
    current: dict[UUID, tuple[str, dict[str, Any]]],
    user: User,
) -> dict[str, str]:
    """id → name for every record the payloads and current values refer to."""
    wanted: dict[Any, set[UUID]] = {}
    sources = [p.applied_payload or p.proposed_payload for p in proposals]
    sources += [p.proposed_payload for p in proposals if p.applied_payload]
    sources += [values for _label, values in current.values()]
    for values in sources:
        for model, ids in _reference_ids(values).items():
            wanted.setdefault(model, set()).update(ids)
    labels: dict[str, str] = {}
    for model, ids in wanted.items():
        attr = getattr(model, _REFERENCE_LABELS[model])
        rows = await session.execute(
            select(model.id, attr).where(model.id.in_(ids), model.user_id == user.id)
        )
        for row_id, name in rows.all():
            labels[str(row_id)] = str(name)
    return labels
