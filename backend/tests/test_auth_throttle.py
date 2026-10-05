"""Per-account login backoff and reset-mail cooldown (#134).

Where a test needs the clock to have moved, it rewrites the row's timestamps
instead of sleeping.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx2 import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli
from app.auth.throttle import AuthThrottle, claim_login_attempt, lock_seconds
from app.config import settings
from tests.conftest import Account, Outbox
from tests.test_password_reset import token_from

FREE = settings.login_backoff_free_failures


async def _login(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/auth/jwt/login", data={"username": email, "password": password})


async def _fail_until_locked(client: AsyncClient, email: str) -> None:
    """Spend the free failures and one more, which earns the first lock."""
    for _ in range(FREE + 1):
        response = await _login(client, email, "wrong password")
        assert response.status_code == 400


async def _rows(session_factory: async_sessionmaker[AsyncSession]) -> list[AuthThrottle]:
    async with session_factory() as session:
        return list(await session.scalars(select(AuthThrottle)))


async def _age_rows(
    session_factory: async_sessionmaker[AsyncSession], prefix: str, **values: object
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(AuthThrottle).where(AuthThrottle.key.startswith(prefix)).values(**values)
        )
        await session.commit()


async def _unlock_now(session_factory: async_sessionmaker[AsyncSession], prefix: str) -> None:
    await _age_rows(session_factory, prefix, locked_until=datetime.now(UTC) - timedelta(seconds=1))


# Backoff schedule.


def test_the_first_failures_are_free() -> None:
    assert [lock_seconds(n) for n in range(FREE + 1)] == [0] * (FREE + 1)


def test_the_lock_doubles_and_is_capped() -> None:
    assert [lock_seconds(FREE + n) for n in range(1, 5)] == [2, 4, 8, 16]
    assert lock_seconds(FREE + 30) == settings.login_backoff_max_seconds
    assert lock_seconds(10**9) == settings.login_backoff_max_seconds


# Login.


async def test_a_locked_account_refuses_even_the_right_password(
    client: AsyncClient, alice: Account
) -> None:
    await _fail_until_locked(client, alice.email)

    response = await _login(client, alice.email, alice.password)
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= lock_seconds(FREE + 1)


async def test_the_free_failures_do_not_lock(client: AsyncClient, alice: Account) -> None:
    for _ in range(FREE):
        await _login(client, alice.email, "wrong password")

    response = await _login(client, alice.email, alice.password)
    assert response.status_code == 200


async def test_an_unknown_address_is_locked_the_same_way(
    client: AsyncClient, alice: Account
) -> None:
    """Otherwise a 429 would tell a guesser that an address has an account."""
    await _fail_until_locked(client, "nobody@example.com")

    response = await _login(client, "nobody@example.com", "anything")
    assert response.status_code == 429


async def test_the_address_is_matched_case_insensitively(
    client: AsyncClient, alice: Account
) -> None:
    await _fail_until_locked(client, alice.email.upper())

    response = await _login(client, alice.email, alice.password)
    assert response.status_code == 429


async def test_accounts_do_not_share_a_lock(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    await _fail_until_locked(client, alice.email)

    response = await _login(client, bob.email, bob.password)
    assert response.status_code == 200


async def test_the_lock_grows_with_each_failure_after_it_ends(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _fail_until_locked(client, alice.email)
    await _unlock_now(session_factory, "login:")

    assert (await _login(client, alice.email, "wrong password")).status_code == 400

    response = await _login(client, alice.email, alice.password)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > lock_seconds(FREE + 1)


async def test_attempts_while_locked_do_not_count(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _fail_until_locked(client, alice.email)
    for _ in range(5):
        assert (await _login(client, alice.email, "wrong password")).status_code == 429

    [row] = await _rows(session_factory)
    assert row.count == FREE + 1


async def test_attempts_while_locked_spend_the_address_budget(
    client: AsyncClient, alice: Account
) -> None:
    """A locked account is no free target: each refusal counts per address."""
    await _fail_until_locked(client, alice.email)
    for _ in range(settings.login_max_failures - (FREE + 1)):
        assert (await _login(client, alice.email, "wrong password")).status_code == 429

    # The address is now over its own budget, whichever account it names.
    response = await _login(client, "nobody@example.com", "anything")
    assert response.status_code == 429


async def test_a_successful_login_clears_the_count(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _fail_until_locked(client, alice.email)
    await _unlock_now(session_factory, "login:")

    assert (await _login(client, alice.email, alice.password)).status_code == 200
    assert await _rows(session_factory) == []


async def test_a_quiet_day_starts_the_count_afresh(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _fail_until_locked(client, alice.email)
    long_ago = datetime.now(UTC) - timedelta(seconds=settings.login_backoff_decay_seconds + 1)
    await _age_rows(session_factory, "login:", last_event_at=long_ago, locked_until=long_ago)

    assert (await _login(client, alice.email, "wrong password")).status_code == 400

    assert (await _login(client, alice.email, alice.password)).status_code == 200


async def test_a_failure_sweeps_rows_a_day_old(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _login(client, "nobody@example.com", "wrong password")
    long_ago = datetime.now(UTC) - timedelta(seconds=settings.login_backoff_decay_seconds + 1)
    await _age_rows(session_factory, "login:", last_event_at=long_ago)

    await _login(client, alice.email, "wrong password")

    [row] = await _rows(session_factory)
    assert row.last_event_at > long_ago


async def test_signed_in_devices_keep_refreshing_while_locked(
    client: AsyncClient, alice: Account
) -> None:
    await _fail_until_locked(client, alice.email)

    response = await client.post("/auth/jwt/refresh", json={"refresh_token": alice.refresh_token})
    assert response.status_code == 200


async def test_the_address_is_not_stored(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _login(client, alice.email, "wrong password")

    [row] = await _rows(session_factory)
    assert row.key.startswith("login:")
    assert "alice" not in row.key


async def test_a_burst_gets_no_more_attempts_than_a_queue(
    alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Arriving together must not let every request reach the password check."""

    async def claim() -> int | None:
        async with session_factory() as session:
            return await claim_login_attempt(session, alice.email)

    results = await asyncio.gather(*(claim() for _ in range(FREE + 10)))

    assert results.count(None) == FREE + 1
    [row] = await _rows(session_factory)
    assert row.count == FREE + 1


async def test_a_password_reset_ends_the_lock(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    await _fail_until_locked(client, alice.email)

    await client.post("/auth/forgot-password", json={"email": alice.email})
    [mail] = outbox.sent
    response = await client.post(
        "/auth/reset-password", json={"token": token_from(mail), "password": "a-fresh-secret"}
    )
    assert response.status_code == 200

    assert (await _login(client, alice.email, "a-fresh-secret")).status_code == 200


# Reset-mail cooldown.


async def test_a_second_reset_request_inside_the_cooldown_sends_nothing(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    first = await client.post("/auth/forgot-password", json={"email": alice.email})
    second = await client.post("/auth/forgot-password", json={"email": alice.email})

    # The same answer both times: the cooldown is not observable from outside.
    assert first.status_code == second.status_code == 202
    assert len(outbox.sent) == 1


async def test_the_cooldown_ends(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.post("/auth/forgot-password", json={"email": alice.email})
    await _unlock_now(session_factory, "reset-mail:")

    await client.post("/auth/forgot-password", json={"email": alice.email})
    assert len(outbox.sent) == 2


async def test_a_failed_delivery_still_starts_the_cooldown(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    outbox.fail = True
    response = await client.post("/auth/forgot-password", json={"email": alice.email})
    assert response.status_code == 202

    outbox.fail = False
    await client.post("/auth/forgot-password", json={"email": alice.email})
    assert outbox.sent == []


async def test_accounts_do_not_share_a_cooldown(
    client: AsyncClient, alice: Account, bob: Account, outbox: Outbox
) -> None:
    await client.post("/auth/forgot-password", json={"email": alice.email})
    await client.post("/auth/forgot-password", json={"email": bob.email})

    assert [mail.to_address for mail in outbox.sent] == [alice.email, bob.email]


async def test_an_unknown_address_adds_no_row(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert await _rows(session_factory) == []


# Operator CLI.


@pytest.fixture
def cli_database(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    monkeypatch.setattr(cli, "_session_factory", session_factory)


@pytest.mark.usefixtures("cli_database")
async def test_unlock_ends_the_lock_and_the_cooldown(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await _fail_until_locked(client, alice.email)
    await client.post("/auth/forgot-password", json={"email": alice.email})

    await cli._unlock(alice.email)

    assert "Cleared" in capsys.readouterr().out
    assert (await _login(client, alice.email, alice.password)).status_code == 200
    await client.post("/auth/forgot-password", json={"email": alice.email})
    assert len(outbox.sent) == 2


@pytest.mark.usefixtures("cli_database")
async def test_unlock_says_when_there_is_nothing_to_clear(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli._unlock("nobody@example.com")

    assert "Nothing to clear" in capsys.readouterr().out
