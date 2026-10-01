"""Sessions (#133): short access tokens, rotating refresh tokens, a real sign-out."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi_users.jwt import generate_jwt
from httpx2 import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import sessions
from app.auth.sessions import AuthSession
from app.auth.users import User
from app.config import settings
from tests.conftest import Account


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _refresh(client: AsyncClient, refresh_token: str) -> tuple[int, dict[str, Any]]:
    response = await client.post("/auth/jwt/refresh", json={"refresh_token": refresh_token})
    return response.status_code, response.json() if response.content else {}


async def _login(client: AsyncClient, account: Account) -> dict[str, Any]:
    response = await client.post(
        "/auth/jwt/login", data={"username": account.email, "password": account.password}
    )
    assert response.status_code == 200
    tokens: dict[str, Any] = response.json()
    return tokens


async def test_login_hands_out_a_short_access_token_and_a_refresh_token(
    client: AsyncClient, alice: Account
) -> None:
    tokens = await _login(client, alice)

    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == settings.access_token_lifetime_seconds
    assert tokens["refresh_token"]
    assert (
        await client.get("/users/me", headers=_bearer(tokens["access_token"]))
    ).status_code == 200


async def test_a_refresh_hands_out_a_working_pair(client: AsyncClient, alice: Account) -> None:
    status, tokens = await _refresh(client, alice.refresh_token)

    assert status == 200
    assert tokens["refresh_token"] != alice.refresh_token
    assert (
        await client.get("/users/me", headers=_bearer(tokens["access_token"]))
    ).status_code == 200
    # Same session, so the access token it replaced is still good until it expires.
    assert (await client.get("/users/me", headers=alice.headers)).status_code == 200

    status, _ = await _refresh(client, tokens["refresh_token"])
    assert status == 200


async def test_two_tabs_refreshing_together_get_the_same_pair(
    client: AsyncClient, alice: Account
) -> None:
    """The second refresh arrives just after the first rotated the token."""
    _, first = await _refresh(client, alice.refresh_token)
    status, second = await _refresh(client, alice.refresh_token)

    assert status == 200
    assert second["refresh_token"] == first["refresh_token"]
    # And the tab that got in first can carry on.
    status, _ = await _refresh(client, first["refresh_token"])
    assert status == 200


async def test_a_refresh_token_used_again_later_ends_the_session(
    client: AsyncClient, alice: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Someone else has a copy: neither holder can go on, both sign in again."""
    monkeypatch.setattr(sessions, "ROTATION_GRACE", timedelta(0))
    _, rotated = await _refresh(client, alice.refresh_token)

    status, body = await _refresh(client, alice.refresh_token)
    assert status == 401
    assert body["detail"] == "REFRESH_TOKEN_INVALID"

    assert (await _refresh(client, rotated["refresh_token"]))[0] == 401
    assert (
        await client.get("/users/me", headers=_bearer(rotated["access_token"]))
    ).status_code == 401


async def test_an_older_refresh_token_is_reuse_even_within_the_grace(
    client: AsyncClient, alice: Account
) -> None:
    _, first = await _refresh(client, alice.refresh_token)
    await _refresh(client, first["refresh_token"])

    assert (await _refresh(client, alice.refresh_token))[0] == 401
    assert (await client.get("/users/me", headers=alice.headers)).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        "garbage",
        "not-a-uuid.0.abc",
        # A real session id and generation with a made-up signature.
        "{sid}.0.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "{sid}.0.ü",
    ],
)
async def test_a_forged_refresh_token_is_rejected(
    client: AsyncClient,
    alice: Account,
    session_factory: async_sessionmaker[AsyncSession],
    token: str,
) -> None:
    async with session_factory() as db:
        sid = await db.scalar(select(AuthSession.id).where(AuthSession.user_id == alice.id))

    assert (await _refresh(client, token.format(sid=sid)))[0] == 401
    # And a forgery is not mistaken for reuse: the real session survives.
    assert (await client.get("/users/me", headers=alice.headers)).status_code == 200


async def test_signing_out_ends_the_session_server_side(
    client: AsyncClient, alice: Account
) -> None:
    response = await client.post("/auth/jwt/logout", json={"refresh_token": alice.refresh_token})

    assert response.status_code == 204
    assert (await client.get("/users/me", headers=alice.headers)).status_code == 401
    assert (await _refresh(client, alice.refresh_token))[0] == 401


async def test_signing_out_leaves_other_devices_signed_in(
    client: AsyncClient, alice: Account
) -> None:
    laptop = await _login(client, alice)

    await client.post("/auth/jwt/logout", json={"refresh_token": alice.refresh_token})

    assert (
        await client.get("/users/me", headers=_bearer(laptop["access_token"]))
    ).status_code == 200


async def test_signing_out_twice_or_with_nonsense_is_harmless(
    client: AsyncClient, alice: Account
) -> None:
    for token in (alice.refresh_token, alice.refresh_token, "garbage"):
        response = await client.post("/auth/jwt/logout", json={"refresh_token": token})
        assert response.status_code == 204


async def test_a_password_change_signs_out_every_other_session(
    client: AsyncClient, alice: Account
) -> None:
    laptop = await _login(client, alice)

    response = await client.post(
        "/users/me/password",
        json={"old_password": alice.password, "new_password": "a-much-better-secret"},
        headers=alice.headers,
    )
    assert response.status_code == 204

    # The session that changed it carries on…
    assert (await client.get("/users/me", headers=alice.headers)).status_code == 200
    assert (await _refresh(client, alice.refresh_token))[0] == 200
    # …every other one is over.
    assert (
        await client.get("/users/me", headers=_bearer(laptop["access_token"]))
    ).status_code == 401
    assert (await _refresh(client, laptop["refresh_token"]))[0] == 401


async def test_a_token_from_before_sessions_is_refused(client: AsyncClient, alice: Account) -> None:
    """The old 270-day tokens carry no `sid`; they must not outlive the deploy."""
    legacy = generate_jwt(
        {"sub": str(alice.id), "aud": sessions.ACCESS_TOKEN_AUDIENCE},
        settings.jwt_secret,
        60 * 60 * 24 * 270,
    )

    assert (await client.get("/users/me", headers=_bearer(legacy))).status_code == 401


async def test_an_access_token_for_someone_elses_session_is_refused(
    client: AsyncClient,
    alice: Account,
    bob: Account,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        bobs_session = await db.scalar(select(AuthSession.id).where(AuthSession.user_id == bob.id))
    forged = generate_jwt(
        {"sub": str(alice.id), "sid": str(bobs_session), "aud": sessions.ACCESS_TOKEN_AUDIENCE},
        settings.jwt_secret,
        60,
    )

    assert (await client.get("/users/me", headers=_bearer(forged))).status_code == 401


async def test_an_expired_session_cannot_be_refreshed_and_is_swept_at_login(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as db:
        await db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == alice.id)
            .values(expires_at=AuthSession.created_at - timedelta(seconds=1))
        )
        await db.commit()

    assert (await _refresh(client, alice.refresh_token))[0] == 401
    assert (await client.get("/users/me", headers=alice.headers)).status_code == 401

    await _login(client, alice)
    async with session_factory() as db:
        remaining = (
            await db.scalars(select(AuthSession).where(AuthSession.user_id == alice.id))
        ).all()
    assert len(remaining) == 1


async def test_a_deactivated_account_cannot_refresh(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as db:
        user = await db.get(User, alice.id)
        assert user is not None
        user.is_active = False
        await db.commit()

    assert (await _refresh(client, alice.refresh_token))[0] == 401
    async with session_factory() as db:
        left = await db.scalar(select(AuthSession.id).where(AuthSession.user_id == alice.id))
    assert left is None
