"""Change history (#142): who changed which field of a record, and when.

Two halves:

* `Versioned` gives every record table a `version` counter that goes up by one
  on every UPDATE. A PATCH that names the version it was edited from is refused
  once someone else has saved in between — the check that turns "two tabs, last
  write silently wins" into a 409 the second tab can act on.
* `AuditEvent` is the append-only log of what actually changed. One row per
  write that changed something, holding only the fields that differ, old and
  new: the edit forms send every field on every save, so logging the request
  instead would bury each real change under twenty unchanged ones.

Nothing is backfilled. The past was never recorded, and inventing a "created"
entry for every existing row would only say what `created_at` already does —
the same stance `deal_stage_events` took.

Both live here rather than under app/models, like Archivable in app/archive.py:
every model imports this module, and app/models would import them all back.

How routers use them:

    row = await _get_owned(...)
    require_live(row, "Contact")
    updates = body.model_dump(exclude_unset=True)
    check_version(row, updates.pop("version", None), "Contact")
    before = snapshot(row)
    ...apply updates...
    record_update(session, user, row, before)
    await session.commit()

The diff is taken from the row, not the request: a form that sends every field
on every save would otherwise log twenty unchanged values per edit, and a
change made on the server's side — a stage move stamping `closed_at`, a rate
cleared with its currency — would never appear at all.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, delete, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, object_mapper
from sqlalchemy.orm.attributes import flag_modified

from app.db import Base

if TYPE_CHECKING:
    from app.auth.users import User


class Versioned:
    """A record whose writes are counted, so a stale one can be told apart.

    SQLAlchemy's `version_id_col` does the counting: every UPDATE it issues is
    `... WHERE id = :id AND version = :loaded`, and sets `version + 1`. Two
    requests that both loaded version 3 cannot both write — the second matches
    no row and raises StaleDataError, which app/main.py answers with 409.
    check_version() below catches the common case (a form opened an hour ago)
    before any work is done; this catches the race in between.
    """

    # server_default for the rows that existed before the column did; new rows
    # are numbered by SQLAlchemy itself, starting at 1.
    version: Mapped[int] = mapped_column(server_default="1")

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.__table__.c.version}  # type: ignore[attr-defined]


class AuditEvent(Base):
    """One write to one record: who made it, when, and what it changed."""

    __tablename__ = "audit_events"
    __table_args__ = (
        # The one question this table is asked: "the history of this record",
        # newest first, for its owner.
        Index(
            "ix_audit_events_entity",
            "user_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # The tenant the record belongs to — what every read is scoped by.
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    # Who made the change. The same person as user_id while each account is its
    # own tenant; a separate column so a second user (T25) needs no migration.
    # SET NULL, so removing that user later leaves the history standing.
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    # "contact", "deal", ... with no foreign key: one table serves nine. The
    # history goes when the record is erased (erase_history below).
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[UUID]
    # update | archive | restore. A free-form String like Deal.stage, held to
    # its values by app/schemas/audit.py.
    action: Mapped[str] = mapped_column(String)
    # {field: {"old": ..., "new": ...}} — only what changed. Empty for archive
    # and restore, which change nothing but the record's state.
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Columns that are bookkeeping rather than content. Changing them is a side
# effect of every write, so listing them would put noise on every entry.
# storage_key and preview_key are where a document's bytes live, not anything
# its owner chose; a new upload shows up as its format and size changing.
_IGNORED = frozenset(
    {
        "id",
        "user_id",
        "version",
        "created_at",
        "updated_at",
        # Task's names for the same two.
        "created",
        "updated",
        # Archiving is an action of its own, not a field edit.
        "archived_at",
        "storage_key",
        "preview_key",
    }
)

Snapshot = dict[str, Any]


def entity_type(row: Versioned) -> str:
    """The name a history entry files `row` under: "contact", "deal", ..."""
    return type(row).__name__.lower()


def check_version(row: Versioned, expected: int | None, label: str) -> None:
    """Refuse a write made from an outdated copy of `row`.

    `expected` is the version the client loaded before editing. None skips the
    check — what a one-field toggle like "done" sends, where the newer value
    winning is the right answer anyway.

    409, like require_live: the request is well formed and the row exists, its
    state has simply moved on. The client's way out is to reload.
    """
    if expected is not None and expected != row.version:
        raise HTTPException(
            status_code=409,
            detail=f"{label} was changed elsewhere since you opened it — reload to see the "
            "latest version",
        )


def _plain(value: Any) -> Any:
    """`value` as JSON can hold it, without losing what it says.

    Decimal goes to a string rather than a float, like every amount the API
    returns: a binary double cannot hold 0.10.
    """
    if isinstance(value, Decimal | UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def snapshot(row: Versioned) -> Snapshot:
    """Every content field of `row` as it stands, to diff against later.

    Many-to-many links are included as sorted id lists under the API's own
    names (`contacts` → `contact_ids`), so re-filing an interaction under
    another deal is a change like any other. Every such link is loaded
    `selectin`, so reading them here issues no query.

    Postgres-generated columns (Deal.expected_value) are left out: the row
    holds their old value until it is refreshed, so they would never differ.
    """
    mapper = object_mapper(row)
    state: Snapshot = {}
    for prop in mapper.column_attrs:
        column = prop.columns[0]
        # Not a column of the table at all: a SQL expression mapped as a read
        # (Deal.has_next_step), which nothing ever writes.
        if not isinstance(column, Column):
            continue
        if prop.key in _IGNORED or column.computed is not None:
            continue
        state[prop.key] = getattr(row, prop.key)
    for rel in mapper.relationships:
        if rel.secondary is None or not rel.uselist:
            continue
        ids = sorted(str(linked.id) for linked in getattr(row, rel.key))
        state[f"{rel.key.removesuffix('s')}_ids"] = ids
    return state


def diff(before: Snapshot, after: Snapshot) -> dict[str, dict[str, Any]]:
    """The fields that differ, each as {"old": ..., "new": ...}."""
    return {
        field: {"old": _plain(old), "new": _plain(after[field])}
        for field, old in before.items()
        if after[field] != old
    }


def record_update(session: AsyncSession, actor: "User", row: Versioned, before: Snapshot) -> None:
    """Log what changed on `row` since `before`, if anything did.

    A save that changed nothing — the same form submitted twice — leaves no
    entry: a history padded with non-events hides the real ones.
    """
    changes = diff(before, snapshot(row))
    if not changes:
        return
    record(session, actor, row, "update", changes)
    # A save that only re-filed the record (contact_ids, ...) writes the link
    # tables and never the row, so the version would not move and a stale copy
    # could undo the change unnoticed. Marking any column dirty forces the
    # UPDATE, and with it the version bump; user_id is one no save ever sets.
    flag_modified(row, "user_id")


def record(
    session: AsyncSession,
    actor: "User",
    row: Versioned,
    action: str,
    changes: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Add one history entry for `row` to the session; the caller commits.

    Same transaction as the change itself, so there is never a change without
    its entry or an entry for a change that rolled back.
    """
    session.add(
        AuditEvent(
            user_id=row.user_id,  # type: ignore[attr-defined]
            actor_id=actor.id,
            entity_type=entity_type(row),
            entity_id=row.id,  # type: ignore[attr-defined]
            action=action,
            changes=changes or {},
        )
    )


async def erase_history(session: AsyncSession, row: Versioned) -> None:
    """Delete `row`'s history along with it.

    DELETE is the erasure (#143). A log that kept every old email address of a
    contact who asked to be forgotten would be the copy that was not erased.
    """
    await session.execute(
        delete(AuditEvent).where(
            AuditEvent.user_id == row.user_id,  # type: ignore[attr-defined]
            AuditEvent.entity_type == entity_type(row),
            AuditEvent.entity_id == row.id,  # type: ignore[attr-defined]
        )
    )
