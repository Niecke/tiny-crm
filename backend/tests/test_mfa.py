"""Two-factor sign-in (#18): setting it up, signing in with it, turning it off.

Codes come from pyotp itself, the way an authenticator app computes them. A
code is good once per 30-second step, and confirming the setup already spends
the current step, so a sign-in right after uses the next step's code — which
the one step of allowed drift accepts.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
from httpx2 import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli
from app.auth import mfa
from app.auth.sessions import AuthSession
from app.auth.users import User
from app.config import settings
from tests.conftest import Account
from tests.test_password_reset import NEW_PASSWORD, _reset_token


@dataclass
class Enrolled:
    account: Account
    secret: str
    recovery_codes: list[str]


def code(secret: str, steps_ahead: int = 0) -> str:
    return pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30 * steps_ahead))


async def enroll(client: AsyncClient, account: Account) -> Enrolled:
    setup = await client.post("/users/me/mfa/setup", headers=account.headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirm = await client.post(
        "/users/me/mfa/confirm", json={"code": code(secret)}, headers=account.headers
    )
    assert confirm.status_code == 200, confirm.text
    return Enrolled(account, secret, confirm.json()["recovery_codes"])


async def forget_last_step(factory: async_sessionmaker[AsyncSession], account: Account) -> None:
    """Let the current step's code be used again, as half a minute later would."""
    async with factory() as session:
        await session.execute(
            update(User).where(User.id == account.id).values(mfa_last_step=None)  # type: ignore[arg-type]
        )
        await session.commit()


async def login(client: AsyncClient, account: Account, password: str | None = None) -> Any:
    response = await client.post(
        "/auth/jwt/login",
        data={"username": account.email, "password": password or account.password},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def session_count(factory: async_sessionmaker[AsyncSession], account: Account) -> int:
    async with factory() as session:
        rows = await session.scalars(
            select(AuthSession.id).where(AuthSession.user_id == account.id)
        )
        return len(rows.all())


@pytest.fixture
async def enrolled(client: AsyncClient, alice: Account) -> Enrolled:
    return await enroll(client, alice)


# Setup


async def test_mfa_is_off_until_set_up(client: AsyncClient, alice: Account) -> None:
    me = await client.get("/users/me", headers=alice.headers)
    assert me.json()["mfa_enabled_at"] is None
    assert "mfa_secret" not in me.json()

    assert "access_token" in await login(client, alice)


async def test_setup_returns_a_scannable_uri(client: AsyncClient, alice: Account) -> None:
    response = await client.post("/users/me/mfa/setup", headers=alice.headers)

    body = response.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/tinyCRM:alice%40example.com?")
    assert f"secret={body['secret']}" in body["otpauth_uri"]


async def test_a_pending_setup_does_not_change_sign_in(client: AsyncClient, alice: Account) -> None:
    await client.post("/users/me/mfa/setup", headers=alice.headers)

    assert "access_token" in await login(client, alice)


async def test_the_secret_is_not_stored_in_plain(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], alice: Account
) -> None:
    secret = (await client.post("/users/me/mfa/setup", headers=alice.headers)).json()["secret"]

    async with session_factory() as session:
        stored = await session.scalar(select(User.mfa_secret).where(User.id == alice.id))  # type: ignore[arg-type]
    assert stored is not None and secret not in stored
    assert mfa.unseal(stored) == secret


async def test_a_wrong_confirmation_code_leaves_mfa_off(
    client: AsyncClient, alice: Account
) -> None:
    secret = (await client.post("/users/me/mfa/setup", headers=alice.headers)).json()["secret"]
    wrong = str((int(code(secret)) + 1) % 1_000_000).zfill(6)

    response = await client.post(
        "/users/me/mfa/confirm", json={"code": wrong}, headers=alice.headers
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "MFA_CODE_INVALID"
    assert "access_token" in await login(client, alice)


async def test_confirm_without_setup_is_refused(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/users/me/mfa/confirm", json={"code": "123456"}, headers=alice.headers
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "MFA_SETUP_NOT_STARTED"


async def test_confirming_turns_mfa_on_and_hands_out_recovery_codes(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    assert len(enrolled.recovery_codes) == mfa.RECOVERY_CODE_COUNT
    assert len(set(enrolled.recovery_codes)) == mfa.RECOVERY_CODE_COUNT

    me = await client.get("/users/me", headers=enrolled.account.headers)
    assert me.json()["mfa_enabled_at"] is not None


async def test_setup_again_while_on_is_refused(client: AsyncClient, enrolled: Enrolled) -> None:
    response = await client.post("/users/me/mfa/setup", headers=enrolled.account.headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "MFA_ALREADY_ENABLED"


async def test_turning_mfa_on_signs_out_every_other_session(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], alice: Account
) -> None:
    other = (await login(client, alice))["access_token"]

    await enroll(client, alice)

    assert (await client.get("/users/me", headers=alice.headers)).status_code == 200
    gone = await client.get("/users/me", headers={"Authorization": f"Bearer {other}"})
    assert gone.status_code == 401
    assert await session_count(session_factory, alice) == 1


# Signing in


async def test_with_mfa_on_a_password_alone_opens_no_session(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], enrolled: Enrolled
) -> None:
    before = await session_count(session_factory, enrolled.account)

    body = await login(client, enrolled.account)

    assert body["mfa_required"] is True
    assert body["expires_in"] == 300
    assert "access_token" not in body
    assert await session_count(session_factory, enrolled.account) == before


async def test_a_correct_code_completes_the_login(client: AsyncClient, enrolled: Enrolled) -> None:
    challenge = await login(client, enrolled.account)

    response = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": code(enrolled.secret, 1)},
    )

    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == enrolled.account.email


async def test_a_wrong_password_still_gets_no_challenge(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    response = await client.post(
        "/auth/jwt/login", data={"username": enrolled.account.email, "password": "nope"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"


async def test_a_wrong_code_is_refused(client: AsyncClient, enrolled: Enrolled) -> None:
    challenge = await login(client, enrolled.account)

    response = await client.post(
        "/auth/jwt/mfa", json={"mfa_token": challenge["mfa_token"], "code": "000000"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "MFA_CODE_INVALID"


async def test_a_code_works_only_once(client: AsyncClient, enrolled: Enrolled) -> None:
    once = code(enrolled.secret, 1)
    first = await login(client, enrolled.account)
    ok = await client.post("/auth/jwt/mfa", json={"mfa_token": first["mfa_token"], "code": once})
    assert ok.status_code == 200

    second = await login(client, enrolled.account)
    replay = await client.post(
        "/auth/jwt/mfa", json={"mfa_token": second["mfa_token"], "code": once}
    )

    assert replay.status_code == 400


async def test_the_confirmation_code_cannot_sign_in(client: AsyncClient, alice: Account) -> None:
    secret = (await client.post("/users/me/mfa/setup", headers=alice.headers)).json()["secret"]
    used = code(secret)
    await client.post("/users/me/mfa/confirm", json={"code": used}, headers=alice.headers)

    challenge = await login(client, alice)
    response = await client.post(
        "/auth/jwt/mfa", json={"mfa_token": challenge["mfa_token"], "code": used}
    )

    assert response.status_code == 400


async def test_code_guesses_run_into_the_account_backoff(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    # The password step counts as one attempt until the code is right too.
    challenge = await login(client, enrolled.account)
    statuses = [
        (
            await client.post(
                "/auth/jwt/mfa", json={"mfa_token": challenge["mfa_token"], "code": "000000"}
            )
        ).status_code
        for _ in range(4)
    ]

    assert statuses == [400, 400, 400, 429]
    # Locked means locked: the right code gets no answer about itself either.
    locked = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": code(enrolled.secret, 1)},
    )
    assert locked.status_code == 429


async def test_a_recovery_code_signs_in_once(client: AsyncClient, enrolled: Enrolled) -> None:
    recovery = enrolled.recovery_codes[0]

    first = await login(client, enrolled.account)
    # Typed back in by hand: case and dashes do not matter.
    typed = recovery.upper().replace("-", " ")
    ok = await client.post("/auth/jwt/mfa", json={"mfa_token": first["mfa_token"], "code": typed})
    assert ok.status_code == 200, ok.text

    second = await login(client, enrolled.account)
    again = await client.post(
        "/auth/jwt/mfa", json={"mfa_token": second["mfa_token"], "code": recovery}
    )
    assert again.status_code == 400


async def test_another_accounts_recovery_code_does_not_work(
    client: AsyncClient, enrolled: Enrolled, bob: Account
) -> None:
    bobs = await enroll(client, bob)
    challenge = await login(client, enrolled.account)

    response = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": bobs.recovery_codes[0]},
    )

    assert response.status_code == 400


# The challenge token


async def test_a_challenge_is_not_an_access_token(client: AsyncClient, enrolled: Enrolled) -> None:
    challenge = await login(client, enrolled.account)

    response = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {challenge['mfa_token']}"}
    )

    assert response.status_code == 401


async def test_an_access_token_is_not_a_challenge(client: AsyncClient, enrolled: Enrolled) -> None:
    access = enrolled.account.headers["Authorization"].removeprefix("Bearer ")

    response = await client.post(
        "/auth/jwt/mfa", json={"mfa_token": access, "code": code(enrolled.secret, 1)}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "MFA_TOKEN_INVALID"


async def test_an_expired_challenge_is_refused(
    client: AsyncClient, enrolled: Enrolled, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mfa, "MFA_TOKEN_LIFETIME", timedelta(seconds=-1))
    challenge = await login(client, enrolled.account)

    response = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": code(enrolled.secret, 1)},
    )

    assert response.status_code == 401


async def test_a_challenge_dies_with_the_setup_it_was_issued_for(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], enrolled: Enrolled
) -> None:
    challenge = await login(client, enrolled.account)
    # Turned off and set up afresh in between, e.g. from another device.
    async with session_factory() as session:
        await mfa.disable(session, enrolled.account.id)
    renewed = await enroll(client, enrolled.account)

    response = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": code(renewed.secret, 1)},
    )

    assert response.status_code == 401


# Managing it


async def test_new_recovery_codes_replace_the_old_ones(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    response = await client.post(
        "/users/me/mfa/recovery-codes",
        json={"password": enrolled.account.password},
        headers=enrolled.account.headers,
    )
    assert response.status_code == 200
    fresh = response.json()["recovery_codes"]
    assert set(fresh).isdisjoint(enrolled.recovery_codes)

    challenge = await login(client, enrolled.account)
    old = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": enrolled.recovery_codes[1]},
    )
    assert old.status_code == 400
    new = await client.post(
        "/auth/jwt/mfa", json={"mfa_token": challenge["mfa_token"], "code": fresh[0]}
    )
    assert new.status_code == 200


async def test_new_recovery_codes_need_the_password(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    response = await client.post(
        "/users/me/mfa/recovery-codes",
        json={"password": "not it"},
        headers=enrolled.account.headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "PASSWORD_INCORRECT"


async def test_turning_mfa_off_needs_password_and_code(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], enrolled: Enrolled
) -> None:
    headers = enrolled.account.headers
    await forget_last_step(session_factory, enrolled.account)

    wrong_password = await client.post(
        "/users/me/mfa/disable",
        json={"password": "not it", "code": code(enrolled.secret)},
        headers=headers,
    )
    wrong_code = await client.post(
        "/users/me/mfa/disable",
        json={"password": enrolled.account.password, "code": "000000"},
        headers=headers,
    )
    assert wrong_password.status_code == 400
    assert wrong_code.status_code == 400

    ok = await client.post(
        "/users/me/mfa/disable",
        json={"password": enrolled.account.password, "code": code(enrolled.secret)},
        headers=headers,
    )
    assert ok.status_code == 204
    assert "access_token" in await login(client, enrolled.account)
    me = await client.get("/users/me", headers=headers)
    assert me.json()["mfa_enabled_at"] is None


async def test_mfa_can_be_turned_off_with_a_recovery_code(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    response = await client.post(
        "/users/me/mfa/disable",
        json={"password": enrolled.account.password, "code": enrolled.recovery_codes[0]},
        headers=enrolled.account.headers,
    )

    assert response.status_code == 204


async def test_one_account_turning_mfa_off_leaves_the_other(
    client: AsyncClient, enrolled: Enrolled, bob: Account
) -> None:
    bobs = await enroll(client, bob)

    await client.post(
        "/users/me/mfa/disable",
        json={"password": enrolled.account.password, "code": enrolled.recovery_codes[0]},
        headers=enrolled.account.headers,
    )

    assert (await login(client, bob))["mfa_required"] is True
    me = await client.get("/users/me", headers=bobs.account.headers)
    assert me.json()["mfa_enabled_at"] is not None


async def test_a_password_reset_leaves_mfa_on(
    client: AsyncClient, enrolled: Enrolled, outbox: Any
) -> None:
    token = await _reset_token(client, enrolled.account.email, outbox)
    reset = await client.post(
        "/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )
    assert reset.status_code == 200

    assert (await login(client, enrolled.account, NEW_PASSWORD))["mfa_required"] is True


async def test_a_secret_sealed_under_an_old_jwt_secret_needs_a_recovery_code(
    client: AsyncClient, enrolled: Enrolled, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "jwt_secret", settings.jwt_secret + "-rotated")
    challenge = await login(client, enrolled.account)

    totp = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": code(enrolled.secret, 1)},
    )
    recovery = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": enrolled.recovery_codes[0]},
    )

    assert totp.status_code == 400
    assert recovery.status_code == 200


# The operator's way out


async def test_cli_disable_mfa(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    enrolled: Enrolled,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_session_factory", session_factory)

    await cli._disable_mfa(enrolled.account.email)
    assert "turned off" in capsys.readouterr().out
    assert "access_token" in await login(client, enrolled.account)

    await cli._disable_mfa(enrolled.account.email)
    assert "no two-factor" in capsys.readouterr().out


# Races and leftovers the review turned up


async def test_a_challenge_dies_with_a_password_change(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    challenge = await login(client, enrolled.account)
    changed = await client.post(
        "/users/me/password",
        json={"old_password": enrolled.account.password, "new_password": NEW_PASSWORD},
        headers=enrolled.account.headers,
    )
    assert changed.status_code == 204

    response = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": code(enrolled.secret, 1)},
    )

    assert response.status_code == 401


async def test_a_challenge_dies_with_a_password_reset(
    client: AsyncClient, enrolled: Enrolled, outbox: Any
) -> None:
    challenge = await login(client, enrolled.account)
    token = await _reset_token(client, enrolled.account.email, outbox)
    await client.post("/auth/reset-password", json={"token": token, "password": NEW_PASSWORD})

    response = await client.post(
        "/auth/jwt/mfa",
        json={"mfa_token": challenge["mfa_token"], "code": enrolled.recovery_codes[0]},
    )

    assert response.status_code == 401


async def test_guesses_at_turning_mfa_off_run_into_the_account_backoff(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    def attempt(code: str) -> Any:
        return client.post(
            "/users/me/mfa/disable",
            json={"password": enrolled.account.password, "code": code},
            headers=enrolled.account.headers,
        )

    statuses = [(await attempt("000000")).status_code for _ in range(5)]

    assert statuses == [400, 400, 400, 400, 429]
    # Locked means locked, and signing in is locked along with it.
    assert (await attempt(enrolled.recovery_codes[0])).status_code == 429
    locked = await client.post(
        "/auth/jwt/login",
        data={"username": enrolled.account.email, "password": enrolled.account.password},
    )
    assert locked.status_code == 429


async def test_password_guesses_for_new_recovery_codes_run_into_the_backoff(
    client: AsyncClient, enrolled: Enrolled
) -> None:
    statuses = [
        (
            await client.post(
                "/users/me/mfa/recovery-codes",
                json={"password": "not it"},
                headers=enrolled.account.headers,
            )
        ).status_code
        for _ in range(5)
    ]

    assert statuses == [400, 400, 400, 400, 429]


async def test_a_right_answer_clears_the_backoff(client: AsyncClient, enrolled: Enrolled) -> None:
    headers = enrolled.account.headers
    for _ in range(2):
        await client.post(
            "/users/me/mfa/recovery-codes", json={"password": "not it"}, headers=headers
        )
    ok = await client.post(
        "/users/me/mfa/recovery-codes",
        json={"password": enrolled.account.password},
        headers=headers,
    )
    assert ok.status_code == 200

    # Back to the free failures: the next wrong one is a 400, not a lock.
    for _ in range(3):
        again = await client.post(
            "/users/me/mfa/recovery-codes", json={"password": "not it"}, headers=headers
        )
        assert again.status_code == 400


async def test_confirming_a_secret_that_was_replaced_meanwhile_is_refused(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], alice: Account
) -> None:
    first = (await client.post("/users/me/mfa/setup", headers=alice.headers)).json()["secret"]
    async with session_factory() as session:
        # What the confirm request loaded and checked its code against.
        stale = await session.get(User, alice.id)
    assert stale is not None
    # A second tab starts setup again before the confirm writes.
    await client.post("/users/me/mfa/setup", headers=alice.headers)

    step = mfa.matching_step(first, code(first))
    assert step is not None
    async with session_factory() as session:
        assert await mfa.enable(session, stale, step) is None

    me = await client.get("/users/me", headers=alice.headers)
    assert me.json()["mfa_enabled_at"] is None


async def test_setup_cannot_replace_a_secret_that_was_just_turned_on(
    session_factory: async_sessionmaker[AsyncSession], enrolled: Enrolled
) -> None:
    # The route's is_enabled() check passed before the other tab's confirm.
    async with session_factory() as session:
        assert not await mfa.begin_setup(session, enrolled.account.id, mfa.seal(mfa.new_secret()))
        stored = await session.scalar(
            select(User.mfa_secret).where(User.id == enrolled.account.id)  # type: ignore[arg-type]
        )
    assert stored is not None and mfa.unseal(stored) == enrolled.secret
