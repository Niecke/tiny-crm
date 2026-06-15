import asyncio

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import Base and all models so Alembic can see the full schema.
# Adding a new model file? Import it here too.
from app.db import Base
from app.config import settings  # noqa: F401
from app.logging_config import configure_logging
from app.models import contact as _contact  # noqa: F401
from app.models import document as _doc  # noqa: F401
from app.models import task as _task  # noqa: F401
from app.models import project as _project  # noqa: F401
from app.auth import users as _auth  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Route Alembic's logging through the shared JSON formatter instead of the
# plain `generic` formatter defined in alembic.ini's [formatters] section.
configure_logging()

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Alembic runs migrations synchronously, but our engine is async.
    # async_engine_from_config creates an async engine; run_sync bridges the gap.
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
