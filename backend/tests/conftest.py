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
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi_users.password import PasswordHelper
from httpx2 import ASGITransport, AsyncClient, Response
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import ratelimit
from app.auth.sessions import open_session
from app.auth.users import User, UserManager
from app.config import settings
from app.db import Base, get_session
from app.jobs import jobs_app
from app.jobs import mail as mail_jobs
from app.mail import Mail, PermanentMailError, TransientMailError, get_mail_sender
from app.main import app

# The shipped placeholder is too short for HS256 and PyJWT warns on every token.
# check_secure_defaults() only runs in the lifespan hook, which tests do not use.
settings.jwt_secret = "test-secret-" + "0" * 52
# UserManager copied the placeholder into its token secrets at import time.
UserManager.reset_password_token_secret = settings.jwt_secret
UserManager.verification_token_secret = settings.jwt_secret
# A developer's backend/.env may hold a real Brevo key; no test sends real mail.
# Tests that need a sender use the `outbox` fixture.
settings.brevo_api_key = None
settings.mail_from_address = "crm@example.com"
settings.app_url = "https://crm.example.com"

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


@pytest.fixture(autouse=True)
async def job_queue(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[InMemoryConnector]:
    """The job queue, in memory: what the API defers lands in `.jobs` and stays
    there until a test runs it with `run_jobs`.

    Autouse, so no test reaches for procrastinate's real tables — the scratch
    database has none, its schema comes from the models.
    """
    # At start-up a worker defers the periodic slot that has just passed. Not
    # here: a housekeeping job turning up in some tests' queues and not in
    # others would make every count of jobs a matter of timing.
    monkeypatch.setitem(jobs_app.periodic_defaults, "max_delay", 0)
    connector = InMemoryConnector()
    # Opened, as the API's lifespan does: the connector notes the loop it
    # belongs to, which deferring after a worker has run relies on.
    with jobs_app.replace_connector(connector):
        async with jobs_app.open_async():
            yield connector


@pytest.fixture
def run_jobs(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> Callable[[], Awaitable[None]]:
    """Run whatever is queued and due, the way the worker would — once, against
    this test's database. A job that failed and waits for its retry is left."""
    monkeypatch.setattr(mail_jobs, "_session_factory", session_factory)

    async def run() -> None:
        await jobs_app.run_worker_async(wait=False, install_signal_handlers=False)

    return run


class Outbox:
    """A MailSender that keeps what it is given.

    `fail` makes it refuse the way Brevo refuses a bad key — for good.
    `unreachable` makes it fail the way a network error does — for now.
    """

    def __init__(self) -> None:
        self.sent: list[Mail] = []
        self.fail = False
        self.unreachable = False

    async def send(self, mail: Mail) -> None:
        if self.unreachable:
            raise TransientMailError("could not reach Brevo: ConnectTimeout")
        if self.fail:
            raise PermanentMailError("Brevo refused the mail: HTTP 401 unauthorized")
        self.sent.append(mail)


@pytest.fixture
def outbox(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> Outbox:
    """Mail lands here instead of at Brevo.

    For the API and the worker alike: the API has to find mail configured
    before it queues anything, and the worker (`run_jobs`) does the sending.
    """
    box = Outbox()
    app.dependency_overrides[get_mail_sender] = lambda: box
    monkeypatch.setattr(mail_jobs, "get_mail_sender", lambda: box)
    return box


@dataclass
class Account:
    """One signed-in user: the id its rows carry, plus ready-made auth headers."""

    id: uuid.UUID
    email: str
    password: str
    headers: dict[str, str]
    refresh_token: str


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
        # Opening the session directly keeps the password hash out of the hot
        # path; the login endpoint itself is covered in test_auth.py.
        tokens = await open_session(session, user.id)
    return Account(
        id=user.id,
        email=email,
        password=TEST_PASSWORD,
        headers={"Authorization": f"Bearer {tokens.access_token}"},
        refresh_token=tokens.refresh_token,
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


async def erase(client: AsyncClient, account: Account, path: str) -> Response:
    """Archive the record at `path`, then DELETE it, and return the DELETE.

    The only order a delete is allowed in (#140): erasing something that was
    never archived is refused. tests/test_archive.py covers that refusal; every
    other test that needs a row gone comes through here.
    """
    archived = await client.post(f"{path}/archive", headers=account.headers)
    assert archived.status_code == 200, archived.text
    return await client.delete(path, headers=account.headers)
