"""The login endpoint and /users/me, exercised through the real password flow."""

from httpx import AsyncClient

from tests.conftest import Account


async def test_login_returns_a_usable_token(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/auth/jwt/login",
        data={"username": alice.email, "password": alice.password},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == alice.email


async def test_the_wrong_password_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/auth/jwt/login",
        data={"username": alice.email, "password": "not the password"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"


async def test_an_unknown_account_cannot_log_in(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/auth/jwt/login",
        data={"username": "nobody@example.com", "password": alice.password},
    )

    assert response.status_code == 400


async def test_users_me_requires_a_token(client: AsyncClient) -> None:
    assert (await client.get("/users/me")).status_code == 401


async def test_a_forged_token_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.get("/users/me", headers={"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401
