"""`python -m app.cli`: creating accounts and inviting them.

The commands' async bodies are driven directly — asyncio.run() cannot nest in
the test's event loop — with the CLI's database and sender pointed at the test's.
"""

from collections.abc import Iterator

import pytest
import typer
from fastapi_users.db import SQLAlchemyUserDatabase
from httpx2 import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli
from app.auth.users import User
from tests.conftest import Outbox
from tests.test_password_reset import token_from


@pytest.fixture
def cli_outbox(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> Iterator[Outbox]:
    box = Outbox()
    monkeypatch.setattr(cli, "_session_factory", session_factory)
    monkeypatch.setattr(cli, "get_mail_sender", lambda: box)
    yield box


async def _user(session_factory: async_sessionmaker[AsyncSession], email: str) -> User | None:
    async with session_factory() as session:
        return await SQLAlchemyUserDatabase(session, User).get_by_email(email)


async def test_create_user_mails_an_invite_that_sets_the_password(
    client: AsyncClient,
    cli_outbox: Outbox,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await cli._create_user("carol@example.com", "Carol", superuser=False, password=None)

    [mail] = cli_outbox.sent
    assert mail.to_address == "carol@example.com"
    assert mail.subject == "Your tinyCRM account"
    assert mail.text.startswith("Hello Carol,")

    response = await client.post(
        "/auth/reset-password",
        json={"token": token_from(mail), "password": "carols-own-secret"},
    )
    assert response.status_code == 200
    login = await client.post(
        "/auth/jwt/login", data={"username": "carol@example.com", "password": "carols-own-secret"}
    )
    assert login.status_code == 200

    user = await _user(session_factory, "carol@example.com")
    assert user is not None and user.is_verified and not user.is_superuser


async def test_set_password_skips_the_invite(
    client: AsyncClient, cli_outbox: Outbox, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await cli._create_user("dave@example.com", None, superuser=True, password="daves-secret")

    assert cli_outbox.sent == []
    login = await client.post(
        "/auth/jwt/login", data={"username": "dave@example.com", "password": "daves-secret"}
    )
    assert login.status_code == 200
    user = await _user(session_factory, "dave@example.com")
    assert user is not None and user.is_superuser


async def test_a_set_password_must_follow_the_rule(
    cli_outbox: Outbox, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(typer.Exit):
        await cli._create_user("erin@example.com", None, superuser=False, password="short")

    assert await _user(session_factory, "erin@example.com") is None


async def test_an_existing_address_is_refused(
    cli_outbox: Outbox, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli._create_user("carol@example.com", None, superuser=False, password=None)

    with pytest.raises(typer.Exit):
        await cli._create_user("carol@example.com", None, superuser=False, password=None)

    assert "already exists" in capsys.readouterr().err
    assert len(cli_outbox.sent) == 1


async def test_without_mail_nothing_is_created(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_session_factory", session_factory)
    monkeypatch.setattr(cli, "get_mail_sender", lambda: None)

    with pytest.raises(typer.Exit):
        await cli._create_user("carol@example.com", None, superuser=False, password=None)

    assert "BREVO_API_KEY" in capsys.readouterr().err
    assert await _user(session_factory, "carol@example.com") is None


async def test_a_failed_invite_keeps_the_account_and_says_how_to_retry(
    cli_outbox: Outbox,
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_outbox.fail = True

    with pytest.raises(typer.Exit):
        await cli._create_user("carol@example.com", None, superuser=False, password=None)

    assert "python -m app.cli invite carol@example.com" in capsys.readouterr().err
    assert await _user(session_factory, "carol@example.com") is not None

    cli_outbox.fail = False
    await cli._invite("carol@example.com")
    assert len(cli_outbox.sent) == 1


async def test_invite_needs_an_existing_account(
    cli_outbox: Outbox, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(typer.Exit):
        await cli._invite("nobody@example.com")

    assert "no user" in capsys.readouterr().err
