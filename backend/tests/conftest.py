"""Test fixtures: a throwaway Postgres, an ASGI client, and two separate users.

The database is a real Postgres — the models use `ARRAY(String)`, `ilike` and
timestamptz, none of which SQLite would exercise honestly. One scratch database
is created for the session and dropped afterwards; its tables are rebuilt before
every test, so tests never see each other's rows.

Point the suite at another server with TEST_DATABASE_URL, e.g.

    TEST_DATABASE_URL=postgresql+asyncpg://crm:crm@localhost:5432/postgres uv run pytest
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi_users.password import PasswordHelper
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import ratelimit
from app.auth.users import User, get_jwt_strategy
from app.config import settings
from app.db import Base, get_session
from app.main import app

# The shipped placeholder is too short for HS256 and PyJWT warns on every token.
# check_secure_defaults() only runs in the lifespan hook, which tests do not use.
settings.jwt_secret = "test-secret-" + "0" * 52

# Server to create the scratch database on. The database named here is only used
# to issue CREATE DATABASE, so any existing one works.
ADMIN_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://crm:crm@localhost:5432/postgres"
)

TEST_PASSWORD = "correct horse battery staple"
# Hashing is deliberately slow, so the suite pays for it once instead of per user.
_PASSWORD_HASH = PasswordHelper().hash(TEST_PASSWORD)


def _with_database(url: str, name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


async def _run_on_admin(statement: str) -> None:
    # CREATE/DROP DATABASE cannot run inside a transaction block.
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql(statement)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A scratch database for this run, dropped when the session ends."""
    name = f"tinycrm_test_{uuid.uuid4().hex[:12]}"
    asyncio.run(_run_on_admin(f'CREATE DATABASE "{name}"'))
    try:
        yield _with_database(ADMIN_URL, name)
    finally:
        asyncio.run(_run_on_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
async def session_factory(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Empty tables for one test.

    The schema comes from the models rather than from Alembic: `alembic check`
    already proves the two agree, and rebuilding per test keeps each one
    independent. ci/smoke.sh runs the real migrations against a real container.
    """
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def reset_login_throttle() -> Iterator[None]:
    """The throttle's counters are module-global, so they outlive a test."""
    ratelimit._failures.clear()
    ratelimit._last_sweep = 0.0
    yield
    ratelimit._failures.clear()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@dataclass
class Account:
    """One signed-in user: the id its rows carry, plus ready-made auth headers."""

    id: uuid.UUID
    email: str
    password: str
    headers: dict[str, str]


async def _create_account(session_factory: async_sessionmaker[AsyncSession], email: str) -> Account:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_PASSWORD_HASH,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    async with session_factory() as session:
        session.add(user)
        await session.commit()

    # Minting the token directly keeps the password hash out of the hot path;
    # the login endpoint itself is covered in test_auth.py.
    token = await get_jwt_strategy().write_token(user)
    return Account(
        id=user.id,
        email=email,
        password=TEST_PASSWORD,
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
async def alice(session_factory: async_sessionmaker[AsyncSession]) -> Account:
    return await _create_account(session_factory, "alice@example.com")


@pytest.fixture
async def bob(session_factory: async_sessionmaker[AsyncSession]) -> Account:
    """A second tenant. Every ownership check is tested from Bob's side."""
    return await _create_account(session_factory, "bob@example.com")


async def create_resource(
    client: AsyncClient, account: Account, path: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """POST `payload` to `path` as `account`, asserting it was created."""
    response = await client.post(path, json=payload, headers=account.headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created
