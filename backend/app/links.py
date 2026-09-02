"""Resolving link-list ids to rows the caller actually owns.

Every many-to-many field on the API is sent as a list of ids. A foreign key
alone would happily accept another tenant's id — and since reads send the linked
record's name back out, that is a data leak rather than untidy data. So every id
in every link list goes through `load_scoped` first.
"""

from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, Table, select
from sqlalchemy.ext.asyncio import AsyncSession


class Owned(Protocol):
    """Any model with an id and an owner — which is all of them."""

    id: Any
    user_id: Any


async def load_scoped[T: Owned](
    session: AsyncSession, model: type[T], ids: list[UUID], user_id: UUID
) -> list[T]:
    """Fetch the given ids of `model` that belong to user_id. 404 on any miss.

    A miss is a 404 rather than a silent drop: quietly ignoring an id the caller
    sent would leave them believing a document is filed against a deal when it
    is not.
    """
    if not ids:
        return []
    result = await session.execute(select(model).where(model.id.in_(ids), model.user_id == user_id))
    found = list(result.scalars().all())
    if len(found) != len(set(ids)):
        raise HTTPException(status_code=404, detail=f"Unknown {model.__name__} id in link list")
    return found


def filter_by_link(
    query: Select[tuple[Any]],
    link_table: Table,
    own_column: str,
    other_column: str,
    target_id: UUID,
) -> Select[tuple[Any]]:
    """Narrow a list query to rows linked to `target_id`.

    Joining the link table rather than loading every row and filtering in
    Python, so "documents on this deal" stays one query and still pages.
    """
    return query.join(
        link_table, link_table.c[own_column] == query.column_descriptions[0]["entity"].id
    ).where(link_table.c[other_column] == target_id)
