from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import Select, func, select
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
