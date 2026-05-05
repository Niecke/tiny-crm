from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# echo=True logs every SQL statement — useful while learning, disable in prod
engine = create_async_engine(settings.database_url, echo=True)

# expire_on_commit=False: objects stay usable after session.commit()
# without this, accessing an attribute after commit triggers a lazy load error
_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session
