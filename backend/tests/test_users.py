"""The account endpoints: profile and the custom password change."""

from httpx2 import AsyncClient

from tests.conftest import Account


async def test_the_profile_reports_the_signed_in_account(
    client: AsyncClient, alice: Account
) -> None:
    response = await client.get("/users/me", headers=alice.headers)

    assert response.status_code == 200
    assert response.json()["email"] == alice.email
    assert response.json()["password_changed_at"] is None
    assert "hashed_password" not in response.json()


async def test_changing_the_password_invalidates_the_old_one(
    client: AsyncClient, alice: Account
) -> None:
    response = await client.post(
        "/users/me/password",
        json={"old_password": alice.password, "new_password": "a-much-better-secret"},
        headers=alice.headers,
    )
    assert response.status_code == 204

    old = await client.post(
        "/auth/jwt/login", data={"username": alice.email, "password": alice.password}
    )
    assert old.status_code == 400

    new = await client.post(
        "/auth/jwt/login",
        data={"username": alice.email, "password": "a-much-better-secret"},
    )
    assert new.status_code == 200

    profile = await client.get("/users/me", headers=alice.headers)
    assert profile.json()["password_changed_at"] is not None


async def test_the_old_password_must_be_right(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/users/me/password",
        json={"old_password": "wrong", "new_password": "a-much-better-secret"},
        headers=alice.headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_OLD_PASSWORD"


async def test_a_too_short_password_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/users/me/password",
        json={"old_password": alice.password, "new_password": "short"},
        headers=alice.headers,
    )

    assert response.status_code == 422


async def test_changing_a_password_needs_a_token(client: AsyncClient) -> None:
    response = await client.post(
        "/users/me/password",
        json={"old_password": "whatever", "new_password": "a-much-better-secret"},
    )

    assert response.status_code == 401
