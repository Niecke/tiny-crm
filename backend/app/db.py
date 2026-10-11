from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import ColumnElement, Select, SQLColumnExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# All models inherit from Base — Alembic uses Base.metadata to detect schema changes.
class Base(DeclarativeBase):
    pass


# echo logs every SQL statement — useful while learning, off unless DB_ECHO=true
engine = create_async_engine(settings.database_url, echo=settings.db_echo)

# expire_on_commit=False: objects stay usable after session.commit()
# without this, accessing an attribute after commit triggers a lazy load error
_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


async def count_rows(session: AsyncSession, query: Select[tuple[Any]]) -> int:
    """How many rows the filtered query matches, ignoring offset and limit.

    Pass the query *before* offset/limit are applied — this wraps it as a
    subquery, so any ordering or joins on it are preserved but irrelevant.
    """
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return total or 0


async def one_at_a_time(session: AsyncSession, key: str) -> None:
    """Wait for any other transaction holding `key`, then hold it until this one ends.

    For work that reads "is this already there?" and then inserts: two requests
    doing that side by side both read "no". A transaction-level advisory lock
    needs no table to lock and no unlock to forget — commit or rollback
    releases it. Two keys hashing alike only wait for each other needlessly.
    """
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))


def escape_like(text: str) -> str:
    """`text` with its own `%`, `_` and `\\` taken literally in a LIKE.

    Without this, searching for "100%" or "first_name" would match far more
    than was typed. The LIKE itself has to name the escape character,
    `escape="\\"` — `contains` does both.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains(column: SQLColumnExpression[Any], text: str) -> ColumnElement[bool]:
    """`column` holds `text` somewhere, whatever its case — the search boxes' match."""
    return column.ilike(f"%{escape_like(text)}%", escape="\\")
