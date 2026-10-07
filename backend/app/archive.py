"""Archive instead of delete (#140).

Every delete used to be final, and it took more than the row with it: the
links pointing at that row went too, so an interaction with a deleted contact
became an interaction with nobody. An archived row stays where it is, and so
does everything that points at it.

Archiving and erasing are kept apart on purpose, because the GDPR answer has to
tell them apart (#143). Archiving puts a record away: out of every list, the
search, the briefing and the dashboard, still there by its id, and back with one
call. `DELETE` erases, exactly as it always has — and only what was archived
first, so one slip of the mouse cannot do it.

An archived record is read-only until it is restored. Editing something that no
list shows any more is how a change gets made and never found again.

*Nothing cascades.* Archiving a company leaves its people where they are, and
archiving a contact leaves the tasks about them open: those are separate
decisions, and making them silently is the opposite of recoverable.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import ColumnElement, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Archivable:
    """A model whose rows can be put away rather than removed."""

    # When it was archived; NULL for everything still in use. A timestamp
    # rather than a flag, like Deal.closed_at: "when did I put this away" is
    # the question a retention period is going to ask (#143).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def archived_is(model: type[Archivable], archived: bool) -> ColumnElement[bool]:
    """The filter behind every list's `?archived=`: one side or the other.

    Never both. A list that mixed the two would need every row to say which it
    is, and every count on the dashboard to say which it counted.
    """
    return model.archived_at.is_not(None) if archived else model.archived_at.is_(None)


def live(model: type[Archivable]) -> ColumnElement[bool]:
    """Not archived — what every list, count and search reads by default."""
    return archived_is(model, False)


def require_live(row: Archivable, label: str) -> None:
    """Refuse to change an archived record.

    409 rather than 404 or 422: the row exists and the request is well formed,
    the state is simply wrong — the same answer a capture gives when it is
    converted twice.
    """
    if row.archived_at is not None:
        raise HTTPException(status_code=409, detail=f"{label} is archived")


def require_archived(row: Archivable, label: str) -> None:
    """Refuse to erase a record that was not archived first."""
    if row.archived_at is None:
        raise HTTPException(
            status_code=409,
            detail=f"{label} is not archived — archive it before deleting it for good",
        )


async def set_archived(session: AsyncSession, row: Archivable, archived: bool) -> None:
    """Archive or restore `row`, and commit.

    Both directions can be repeated without harm. Archiving again keeps the
    first timestamp: it says when the record was put away, not when someone
    last pressed the button.
    """
    if not archived:
        row.archived_at = None
    elif row.archived_at is None:
        row.archived_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(row)
