"""Unique tags across active records (#290)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import get_session
from app.models.contact import Contact
from app.models.document import Document
from app.models.interaction import Interaction
from app.models.task import Task

router = APIRouter(prefix="/tags", tags=["tags"])


def _tag_query(model: Any, user_id: UUID) -> Select[tuple[str]]:
    return select(func.unnest(model.tags).label("tag")).where(
        model.user_id == user_id,
        model.archived_at.is_(None),
        func.cardinality(model.tags) > 0,
    )


@router.get("", response_model=list[str])
@router.get("/", response_model=list[str], include_in_schema=False)
async def list_tags(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> list[str]:
    """All distinct tags currently in use across non-archived records."""
    u = union(
        _tag_query(Contact, user.id),
        _tag_query(Task, user.id),
        _tag_query(Interaction, user.id),
        _tag_query(Document, user.id),
    ).subquery()

    q = (
        select(u.c.tag)
        .where(u.c.tag.is_not(None), u.c.tag != "")
        .order_by(func.lower(u.c.tag).asc(), u.c.tag.asc())
    )
    result = await session.execute(q)
    return list(result.scalars().all())
