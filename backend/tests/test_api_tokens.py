"""API token management (#320): make, list, revoke — and what a token may not do.

The agent routes that accept a token are covered in test_agent_api.py.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx2 import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.api_tokens import ApiToken, hash_token
from tests.conftest import Account, Outbox
from tests.test_password_reset import NEW_PASSWORD, token_from

URL = "/users/me/api-tokens/"

RunJobs = Callable[[], Awaitable[None]]


async def make(
    client: AsyncClient, account: Account, name: str = "pi-agent", **body: object
) -> dict[str, Any]:
    response = await client.post(URL, json={"name": name, **body}, headers=account.headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_creating_returns_the_secret_once(client: AsyncClient, alice: Account) -> None:
    created = await make(client, alice)

    assert created["token"].startswith("tc_live_")
    assert created["status"] == "active"
    assert created["scopes"] == ["read"]
    assert created["last_used_at"] is None

    listed = (await client.get(URL, headers=alice.headers)).json()
    assert [t["id"] for t in listed] == [created["id"]]
    assert "token" not in listed[0]
    assert created["token"] not in (await client.get(URL, headers=alice.headers)).text


async def test_only_the_hash_is_stored(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    created = await make(client, alice)

    async with session_factory() as session:
        [row] = (await session.scalars(select(ApiToken))).all()
    assert row.token_hash == hash_token(created["token"])
    assert len(row.token_hash) == 64
    assert created["token"] not in (row.token_hash, row.name)


async def test_every_token_is_different(client: AsyncClient, alice: Account) -> None:
    first = await make(client, alice)
    second = await make(client, alice)
    assert first["token"] != second["token"]
    listed = (await client.get(URL, headers=alice.headers)).json()
    assert [t["id"] for t in listed] == [second["id"], first["id"]]  # newest first


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_a_bad_name_is_refused(client: AsyncClient, alice: Account, name: str) -> None:
    response = await client.post(URL, json={"name": name}, headers=alice.headers)
    assert response.status_code == 422


async def test_the_name_is_trimmed(client: AsyncClient, alice: Account) -> None:
    assert (await make(client, alice, name="  scraper  "))["name"] == "scraper"


async def test_an_expiry_in_the_past_is_refused(client: AsyncClient, alice: Account) -> None:
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    response = await client.post(URL, json={"name": "x", "expires_at": past}, headers=alice.headers)
    assert response.status_code == 422


async def test_an_expiry_without_a_timezone_is_refused(client: AsyncClient, alice: Account) -> None:
    naive = (datetime.now() + timedelta(days=1)).replace(tzinfo=None).isoformat()
    response = await client.post(
        URL, json={"name": "x", "expires_at": naive}, headers=alice.headers
    )
    assert response.status_code == 422


async def test_scopes_are_not_client_settable(client: AsyncClient, alice: Account) -> None:
    created = await make(client, alice, scopes=["write"])
    assert created["scopes"] == ["read"]


async def test_a_token_past_its_expiry_is_listed_as_expired(
    client: AsyncClient, alice: Account, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    created = await make(
        client, alice, expires_at=(datetime.now(UTC) + timedelta(days=1)).isoformat()
    )
    async with session_factory() as session:
        row = await session.get(ApiToken, created["id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    [listed] = (await client.get(URL, headers=alice.headers)).json()
    assert listed["status"] == "expired"


async def test_revoking_marks_the_token_and_is_idempotent(
    client: AsyncClient, alice: Account
) -> None:
    created = await make(client, alice)

    first = await client.post(f"{URL}{created['id']}/revoke", headers=alice.headers)
    assert first.status_code == 200
    assert first.json()["status"] == "revoked"
    revoked_at = first.json()["revoked_at"]
    assert revoked_at is not None

    again = await client.post(f"{URL}{created['id']}/revoke", headers=alice.headers)
    assert again.status_code == 200
    assert again.json()["revoked_at"] == revoked_at
    # Still listed, as history.
    assert [t["status"] for t in (await client.get(URL, headers=alice.headers)).json()] == [
        "revoked"
    ]


async def test_a_revoked_token_is_refused_on_its_next_use(
    client: AsyncClient, alice: Account
) -> None:
    created = await make(client, alice)
    bearer = {"Authorization": f"Bearer {created['token']}"}
    assert (await client.get("/v1/agent/tasks/today", headers=bearer)).status_code == 200

    await client.post(f"{URL}{created['id']}/revoke", headers=alice.headers)

    assert (await client.get("/v1/agent/tasks/today", headers=bearer)).status_code == 401


async def test_another_users_token_is_not_found(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    created = await make(client, alice)

    assert (await client.get(URL, headers=bob.headers)).json() == []
    response = await client.post(f"{URL}{created['id']}/revoke", headers=bob.headers)
    assert response.status_code == 404
    [listed] = (await client.get(URL, headers=alice.headers)).json()
    assert listed["status"] == "active"


async def test_an_unknown_id_is_not_found(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        f"{URL}00000000-0000-0000-0000-000000000000/revoke", headers=alice.headers
    )
    assert response.status_code == 404


async def test_management_needs_a_signed_in_session(client: AsyncClient, alice: Account) -> None:
    created = await make(client, alice)
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(URL, json={"name": "x"})).status_code == 401
    assert (await client.post(f"{URL}{created['id']}/revoke")).status_code == 401


async def test_a_token_cannot_manage_tokens_or_read_the_account(
    client: AsyncClient, alice: Account
) -> None:
    created = await make(client, alice)
    for headers in (
        {"Authorization": f"Bearer {created['token']}"},
        {"X-API-Key": created["token"]},
    ):
        assert (await client.get(URL, headers=headers)).status_code == 401
        assert (await client.post(URL, json={"name": "x"}, headers=headers)).status_code == 401
        revoke = await client.post(f"{URL}{created['id']}/revoke", headers=headers)
        assert revoke.status_code == 401
        assert (await client.get("/users/me", headers=headers)).status_code == 401
        assert (await client.get("/contacts/", headers=headers)).status_code == 401
        assert (await client.get("/briefing/", headers=headers)).status_code == 401


async def test_a_password_reset_revokes_every_token(
    client: AsyncClient, alice: Account, bob: Account, outbox: Outbox, run_jobs: RunJobs
) -> None:
    mine = await make(client, alice)
    other = await make(client, alice, name="second")
    bobs = await make(client, bob)

    await client.post("/auth/forgot-password", json={"email": alice.email})
    await run_jobs()
    reset = await client.post(
        "/auth/reset-password",
        json={"token": token_from(outbox.sent[0]), "password": NEW_PASSWORD},
    )
    assert reset.status_code == 200

    for created in (mine, other):
        bearer = {"Authorization": f"Bearer {created['token']}"}
        assert (await client.get("/v1/agent/tasks/today", headers=bearer)).status_code == 401
    bobs_bearer = {"Authorization": f"Bearer {bobs['token']}"}
    assert (await client.get("/v1/agent/tasks/today", headers=bobs_bearer)).status_code == 200


async def test_a_password_change_leaves_the_tokens(client: AsyncClient, alice: Account) -> None:
    created = await make(client, alice)

    changed = await client.post(
        "/users/me/password",
        json={"old_password": alice.password, "new_password": NEW_PASSWORD},
        headers=alice.headers,
    )
    assert changed.status_code == 204

    bearer = {"Authorization": f"Bearer {created['token']}"}
    assert (await client.get("/v1/agent/tasks/today", headers=bearer)).status_code == 200
