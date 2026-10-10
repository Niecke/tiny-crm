"""Password reset and email verification, from the request to the new login.

The request only queues the mail; the worker sends it (app/jobs/mail.py). The
tests run the queue with `run_jobs` and take the reset link out of the mail
itself (the `outbox` fixture), so they cover what the recipient actually
receives.
"""

import logging
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Request
from httpx2 import AsyncClient
from procrastinate.exceptions import ConnectorException
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.throttle import clear_reset_mail
from app.auth.users import User, UserManager
from app.config import settings
from app.jobs import MAIL_QUEUE
from app.jobs.mail import send_password_reset
from app.mail import Mail
from tests.conftest import Account, Outbox

NEW_PASSWORD = "a-much-better-secret"

RunJobs = Callable[[], Awaitable[None]]


def token_from(mail: Mail) -> str:
    """The token in the mail's link, the way the frontend page will read it."""
    link = next(line for line in mail.text.splitlines() if line.startswith("https://"))
    parsed = urlparse(link)
    assert f"{parsed.scheme}://{parsed.netloc}" == "https://crm.example.com"
    assert parsed.path == "/reset-password"
    # In the fragment, which the browser never sends to a server.
    assert parsed.query == ""
    return parse_qs(parsed.fragment)["token"][0]


async def _reset_token(client: AsyncClient, email: str, outbox: Outbox, run_jobs: RunJobs) -> str:
    response = await client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    await run_jobs()
    assert len(outbox.sent) == 1
    return token_from(outbox.sent[0])


async def test_forgot_password_mails_a_reset_link(
    client: AsyncClient, alice: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    await client.post("/auth/forgot-password", json={"email": alice.email})
    await run_jobs()

    [mail] = outbox.sent
    assert mail.to_address == alice.email
    assert mail.subject == "Reset your tinyCRM password"
    assert "expires in 12 hours" in mail.text
    assert token_from(mail) in mail.html


async def test_a_reset_replaces_the_password(
    client: AsyncClient, alice: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    token = await _reset_token(client, alice.email, outbox, run_jobs)

    response = await client.post(
        "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 200

    old = await client.post(
        "/auth/jwt/login", data={"username": alice.email, "password": alice.password}
    )
    assert old.status_code == 400
    new = await client.post(
        "/auth/jwt/login", data={"username": alice.email, "password": NEW_PASSWORD}
    )
    assert new.status_code == 200

    fresh = {"Authorization": f"Bearer {new.json()['access_token']}"}
    profile = await client.get("/users/me", headers=fresh)
    assert profile.json()["password_changed_at"] is not None


async def test_a_reset_signs_out_every_session(
    client: AsyncClient, alice: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    """#133: whoever reset the password need not be whoever is signed in."""
    token = await _reset_token(client, alice.email, outbox, run_jobs)
    await client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})

    assert (await client.get("/users/me", headers=alice.headers)).status_code == 401
    refresh = await client.post("/auth/jwt/refresh", json={"refresh_token": alice.refresh_token})
    assert refresh.status_code == 401


async def test_an_unknown_address_gets_the_same_answer(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
) -> None:
    response = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    await run_jobs()

    assert response.status_code == 202
    assert job_queue.jobs == {}
    assert outbox.sent == []


# The request and the queue.


async def test_the_request_queues_the_mail_and_sends_nothing(
    client: AsyncClient, alice: Account, outbox: Outbox, job_queue: InMemoryConnector
) -> None:
    """Waiting for Brevo in the request made known addresses answer later than
    unknown ones (#206). The request must be done before any mail is."""
    response = await client.post("/auth/forgot-password", json={"email": alice.email})

    assert response.status_code == 202
    assert outbox.sent == []
    [job] = job_queue.jobs.values()
    assert job["task_name"] == "send_password_reset"
    assert job["queue_name"] == MAIL_QUEUE
    assert job["status"] == "todo"


async def test_the_job_carries_no_credential(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
) -> None:
    """Job rows are in the nightly backup; the token is minted at send time."""
    token = await _reset_token(client, alice.email, outbox, run_jobs)

    [job] = job_queue.jobs.values()
    assert set(job["args"]) == {"user_id", "requested_at"}
    assert job["args"]["user_id"] == str(alice.id)
    assert token not in str(job)


async def test_asking_again_cannot_stack_mails_for_one_account(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The cooldown has run out, but the first mail is still waiting to be sent."""
    await client.post("/auth/forgot-password", json={"email": alice.email})
    async with session_factory() as session:
        await clear_reset_mail(session, alice.email)

    response = await client.post("/auth/forgot-password", json={"email": alice.email})

    assert response.status_code == 202
    assert len(job_queue.jobs) == 1
    assert "a mail is already queued" in caplog.text
    await run_jobs()
    assert len(outbox.sent) == 1


async def test_a_queue_that_is_down_still_answers_202(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    job_queue: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 500 for known addresses only would tell an outsider which exist."""

    async def refuse(*args: object, **kwargs: object) -> None:
        raise ConnectorException("connection refused")

    monkeypatch.setattr(job_queue, "defer_jobs_all", refuse)

    response = await client.post("/auth/forgot-password", json={"email": alice.email})

    assert response.status_code == 202
    assert "Password reset mail" in caplog.text and "not queued" in caplog.text


async def test_without_mail_configured_a_request_is_logged_and_dropped(
    client: AsyncClient,
    alice: Account,
    job_queue: InMemoryConnector,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = await client.post("/auth/forgot-password", json={"email": alice.email})

    assert response.status_code == 202
    assert "mail is not configured (BREVO_API_KEY)" in caplog.text
    assert job_queue.jobs == {}


# The worker's side: what happens to a queued mail.


def _the_job(job_queue: InMemoryConnector) -> dict[str, object]:
    [job] = job_queue.jobs.values()
    return dict(job)


async def _queue_reset(account: Account, *, age: timedelta = timedelta(0)) -> None:
    """Queue the job directly, as if the request had come in `age` ago."""
    asked = datetime.now(UTC) - age
    await send_password_reset.defer_async(user_id=str(account.id), requested_at=asked.isoformat())


async def test_a_refused_mail_fails_the_job_at_once(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
) -> None:
    """A bad key or an unverified sender: the same answer every time."""
    outbox.fail = True

    response = await client.post("/auth/forgot-password", json={"email": alice.email})
    await run_jobs()

    assert response.status_code == 202
    job = _the_job(job_queue)
    assert job["status"] == "failed"
    assert job["attempts"] == 1


async def test_an_unreachable_brevo_is_tried_again(
    alice: Account, outbox: Outbox, run_jobs: RunJobs, job_queue: InMemoryConnector
) -> None:
    outbox.unreachable = True
    await _queue_reset(alice)
    await run_jobs()

    job = job_queue.jobs[1]
    assert job["status"] == "todo"
    assert job["attempts"] == 1
    assert job["scheduled_at"] > datetime.now(UTC)

    # Brevo is back, and the wait is over.
    outbox.unreachable = False
    job["scheduled_at"] = None
    await run_jobs()

    assert job["status"] == "succeeded"
    assert [mail.to_address for mail in outbox.sent] == [alice.email]


async def test_retrying_ends(
    alice: Account, outbox: Outbox, run_jobs: RunJobs, job_queue: InMemoryConnector
) -> None:
    outbox.unreachable = True
    await _queue_reset(alice)

    runs = 0
    while job_queue.jobs[1]["status"] == "todo":
        job_queue.jobs[1]["scheduled_at"] = None
        await run_jobs()
        runs += 1
        assert runs <= 10, "the job is retried without end"

    assert job_queue.jobs[1]["status"] == "failed"
    assert runs == 5


async def test_a_stale_mail_is_dropped(
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reset link an hour after the click answers a question nobody asks."""
    await _queue_reset(alice, age=timedelta(seconds=settings.mail_max_age_seconds + 60))
    await run_jobs()

    assert outbox.sent == []
    # Done, not failed: there is nothing to diagnose and nothing to retry.
    assert _the_job(job_queue)["status"] == "succeeded"
    assert "dropped: requested 31 minutes ago" in caplog.text


async def test_a_mail_inside_the_age_limit_is_sent(
    alice: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    await _queue_reset(alice, age=timedelta(seconds=settings.mail_max_age_seconds - 60))
    await run_jobs()

    assert len(outbox.sent) == 1


async def test_an_account_deactivated_in_between_gets_no_mail(
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _queue_reset(alice)
    async with session_factory() as session:
        user = await session.get(User, alice.id)
        assert user is not None
        user.is_active = False
        await session.commit()

    await run_jobs()

    assert outbox.sent == []
    assert _the_job(job_queue)["status"] == "succeeded"


async def test_a_password_changed_in_between_still_gets_a_working_link(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The token is bound to the hash at send time, not at request time."""
    await client.post("/auth/forgot-password", json={"email": alice.email})
    async with session_factory() as session:
        user = await session.get(User, alice.id)
        assert user is not None
        user.hashed_password = "changed-while-the-mail-was-queued"
        await session.commit()

    await run_jobs()

    response = await client.post(
        "/auth/reset-password",
        json={"token": token_from(outbox.sent[0]), "password": NEW_PASSWORD},
    )
    assert response.status_code == 200


async def test_a_worker_without_mail_settings_fails_the_job(
    alice: Account, run_jobs: RunJobs, job_queue: InMemoryConnector
) -> None:
    """The API only queues with mail configured, so this is a worker deployed
    with different settings — nothing a retry would fix."""
    await _queue_reset(alice)
    await run_jobs()

    job = _the_job(job_queue)
    assert job["status"] == "failed"
    assert job["attempts"] == 1


async def test_a_reset_token_works_only_once(
    client: AsyncClient, alice: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    token = await _reset_token(client, alice.email, outbox, run_jobs)
    first = await client.post(
        "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )
    assert first.status_code == 200

    # The token carries a fingerprint of the old hash, which the reset replaced.
    second = await client.post(
        "/auth/reset-password", json={"token": token, "password": "yet-another-secret"}
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "RESET_PASSWORD_BAD_TOKEN"


async def test_a_forged_reset_token_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/auth/reset-password", json={"token": "not.a.token", "password": NEW_PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "RESET_PASSWORD_BAD_TOKEN"


async def test_a_reset_enforces_the_password_rule(
    client: AsyncClient, alice: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    token = await _reset_token(client, alice.email, outbox, run_jobs)

    response = await client.post("/auth/reset-password", json={"token": token, "password": "short"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RESET_PASSWORD_INVALID_PASSWORD"
    login = await client.post(
        "/auth/jwt/login", data={"username": alice.email, "password": alice.password}
    )
    assert login.status_code == 200


async def test_the_token_never_reaches_the_logs(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        token = await _reset_token(client, alice.email, outbox, run_jobs)
        await client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})

    assert "Password reset mail queued" in caplog.text
    assert "Password reset mail sent" in caplog.text
    assert token not in caplog.text


async def _mark_unverified(
    session_factory: async_sessionmaker[AsyncSession], account: Account
) -> None:
    async with session_factory() as session:
        user = await session.get(User, account.id)
        assert user is not None
        user.is_verified = False
        await session.commit()


async def test_a_reset_verifies_the_address(
    client: AsyncClient,
    alice: Account,
    outbox: Outbox,
    run_jobs: RunJobs,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _mark_unverified(session_factory, alice)
    token = await _reset_token(client, alice.email, outbox, run_jobs)

    await client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})

    # The reset ended Alice's old session; sign in with the new password.
    login = await client.post(
        "/auth/jwt/login", data={"username": alice.email, "password": NEW_PASSWORD}
    )
    fresh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = await client.get("/users/me", headers=fresh)
    assert profile.json()["is_verified"] is True


@pytest.fixture
def verify_tokens(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Verification tokens are not mailed; pick them up from the hook."""
    tokens: list[str] = []
    original = UserManager.on_after_request_verify

    async def capture(
        self: UserManager, user: User, token: str, request: Request | None = None
    ) -> None:
        tokens.append(token)
        await original(self, user, token, request)

    monkeypatch.setattr(UserManager, "on_after_request_verify", capture)
    yield tokens


async def test_verification_marks_the_account_verified(
    client: AsyncClient,
    alice: Account,
    session_factory: async_sessionmaker[AsyncSession],
    verify_tokens: list[str],
) -> None:
    await _mark_unverified(session_factory, alice)

    response = await client.post("/auth/request-verify-token", json={"email": alice.email})
    assert response.status_code == 202
    assert len(verify_tokens) == 1

    verified = await client.post("/auth/verify", json={"token": verify_tokens[0]})
    assert verified.status_code == 200
    assert verified.json()["is_verified"] is True


async def test_a_verified_account_gets_no_new_token(
    client: AsyncClient, alice: Account, verify_tokens: list[str]
) -> None:
    response = await client.post("/auth/request-verify-token", json={"email": alice.email})

    assert response.status_code == 202
    assert verify_tokens == []
