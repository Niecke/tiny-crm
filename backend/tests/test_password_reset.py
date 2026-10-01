"""Password reset and email verification, from the request to the new login.

The reset link is taken out of the mail itself (the `outbox` fixture), so these
tests cover what the recipient actually receives.
"""

import logging
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Request
from httpx2 import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.users import User, UserManager
from app.mail import Mail
from tests.conftest import Account, Outbox

NEW_PASSWORD = "a-much-better-secret"


def token_from(mail: Mail) -> str:
    """The token in the mail's link, the way the frontend page will read it."""
    link = next(line for line in mail.text.splitlines() if line.startswith("https://"))
    parsed = urlparse(link)
    assert f"{parsed.scheme}://{parsed.netloc}" == "https://crm.example.com"
    assert parsed.path == "/reset-password"
    # In the fragment, which the browser never sends to a server.
    assert parsed.query == ""
    return parse_qs(parsed.fragment)["token"][0]


async def _reset_token(client: AsyncClient, email: str, outbox: Outbox) -> str:
    response = await client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    assert len(outbox.sent) == 1
    return token_from(outbox.sent[0])


async def test_forgot_password_mails_a_reset_link(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    await client.post("/auth/forgot-password", json={"email": alice.email})

    [mail] = outbox.sent
    assert mail.to_address == alice.email
    assert mail.subject == "Reset your tinyCRM password"
    assert "expires in 12 hours" in mail.text
    assert token_from(mail) in mail.html


async def test_a_reset_replaces_the_password(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    token = await _reset_token(client, alice.email, outbox)

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
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    """#133: whoever reset the password need not be whoever is signed in."""
    token = await _reset_token(client, alice.email, outbox)
    await client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})

    assert (await client.get("/users/me", headers=alice.headers)).status_code == 401
    refresh = await client.post("/auth/jwt/refresh", json={"refresh_token": alice.refresh_token})
    assert refresh.status_code == 401


async def test_an_unknown_address_gets_the_same_answer(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    response = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert outbox.sent == []


async def test_a_failed_delivery_still_answers_202(
    client: AsyncClient, alice: Account, outbox: Outbox, caplog: pytest.LogCaptureFixture
) -> None:
    """A 500 for known addresses only would tell an outsider which exist."""
    outbox.fail = True

    response = await client.post("/auth/forgot-password", json={"email": alice.email})

    assert response.status_code == 202
    assert "Password reset mail" in caplog.text and "not sent" in caplog.text


async def test_without_mail_configured_a_request_is_logged_and_dropped(
    client: AsyncClient, alice: Account, caplog: pytest.LogCaptureFixture
) -> None:
    response = await client.post("/auth/forgot-password", json={"email": alice.email})

    assert response.status_code == 202
    assert "mail is not configured (BREVO_API_KEY)" in caplog.text


async def test_a_reset_token_works_only_once(
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    token = await _reset_token(client, alice.email, outbox)
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
    client: AsyncClient, alice: Account, outbox: Outbox
) -> None:
    token = await _reset_token(client, alice.email, outbox)

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
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        token = await _reset_token(client, alice.email, outbox)
        await client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})

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
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _mark_unverified(session_factory, alice)
    token = await _reset_token(client, alice.email, outbox)

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
