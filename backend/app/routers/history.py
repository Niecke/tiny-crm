"""GET /history/{entity_type}/{entity_id}: what changed on one record, and who.

The read side of the change history (#142). It feeds the field-change entries
on the unified timeline (T15); the log itself is written by app/audit.py from
inside each write, never through here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import Record
from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.models import (
    AuditEvent,
    Capture,
    Contact,
    Deal,
    Document,
    Interaction,
    Organization,
    Project,
    Task,
    Watch,
)
from app.schemas.audit import AuditEventRead, EntityType
from app.schemas.page import Page

router = APIRouter(prefix="/history", tags=["history"])

MODELS: dict[str, type[Record]] = {
    "contact": Contact,
    "organization": Organization,
    "deal": Deal,
    "task": Task,
    "interaction": Interaction,
    "project": Project,
    "document": Document,
    "watch": Watch,
    "capture": Capture,
}


@router.get("/{entity_type}/{entity_id}", response_model=Page[AuditEventRead])
async def list_history(
    entity_type: EntityType,
    entity_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[AuditEventRead]:
    """The record's changes, newest first. Archived records keep theirs.

    404 for a record that is not the caller's, exactly as its own GET answers:
    an empty page instead would confirm that the id exists somewhere.
    """
    row = await session.get(MODELS[entity_type], entity_id)
    if row is None or row.user_id != user.id:  # type: ignore[attr-defined]
        raise HTTPException(status_code=404, detail=f"{entity_type.capitalize()} not found")

    q = select(AuditEvent).where(
        AuditEvent.user_id == user.id,
        AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id == entity_id,
    )
    total = await count_rows(session, q)
    result = await session.execute(
        q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.asc()).offset(skip).limit(limit)
    )
    return Page[AuditEventRead](
        items=[AuditEventRead.model_validate(e) for e in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )
