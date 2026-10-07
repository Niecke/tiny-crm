"""Deals with no next step (T43, #116).

An open deal with no open task and nothing planned is invisible: nothing in
the app would ever bring it up again. `has_next_step` on every deal read says
which ones those are, and `?stalled=true` lists them.

The flag is computed per query, never stored, so these tests change the task
or interaction through its own endpoint and read the deal back — the case a
cached flag would get wrong.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from httpx2 import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.deal import Deal
from tests.conftest import Account, create_resource

Sessions = async_sessionmaker[AsyncSession]


async def _deal(client: AsyncClient, account: Account, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": "Website relaunch"}
    payload.update(fields)
    return await create_resource(client, account, "/deals/", payload)


async def _read(client: AsyncClient, account: Account, deal_id: str) -> dict[str, Any]:
    response = await client.get(f"/deals/{deal_id}", headers=account.headers)
    assert response.status_code == 200, response.text
    deal: dict[str, Any] = response.json()
    return deal


async def _interaction(
    client: AsyncClient, account: Account, deal_id: str, at: datetime, **fields: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subject": "Call about the relaunch",
        "kind": "call",
        "occurred_at": at.isoformat(),
        "deal_ids": [deal_id],
    }
    payload.update(fields)
    return await create_resource(client, account, "/interactions/", payload)


async def _age(session_factory: Sessions, deal: dict[str, Any], days: int) -> None:
    async with session_factory() as session:
        await session.execute(
            update(Deal)
            .where(Deal.id == UUID(deal["id"]))
            .values(stage_changed_at=datetime.now(UTC) - timedelta(days=days))
        )
        await session.commit()


# --- has_next_step -----------------------------------------------------------


async def test_a_new_deal_has_no_next_step(client: AsyncClient, alice: Account) -> None:
    deal = await _deal(client, alice)

    assert deal["has_next_step"] is False


async def test_an_open_task_is_a_next_step_until_it_is_done(
    client: AsyncClient, alice: Account
) -> None:
    deal = await _deal(client, alice)

    task = await create_resource(
        client, alice, "/tasks/", {"title": "Send the proposal", "deal_id": deal["id"]}
    )
    assert (await _read(client, alice, deal["id"]))["has_next_step"] is True

    done = await client.patch(f"/tasks/{task['id']}", json={"done": True}, headers=alice.headers)
    assert done.status_code == 200, done.text
    # Nobody told the deal; it is asked again on every read.
    assert (await _read(client, alice, deal["id"]))["has_next_step"] is False


async def test_an_overdue_task_still_counts(client: AsyncClient, alice: Account) -> None:
    """Late is not forgotten — the overdue section already names it."""
    deal = await _deal(client, alice)
    await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Chase the signature",
            "deal_id": deal["id"],
            "due_date": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
        },
    )

    assert (await _read(client, alice, deal["id"]))["has_next_step"] is True


async def test_a_planned_interaction_is_a_next_step_and_a_past_one_is_not(
    client: AsyncClient, alice: Account
) -> None:
    planned = await _deal(client, alice, title="Planned")
    logged = await _deal(client, alice, title="Logged")
    ticked = await _deal(client, alice, title="Ticked off ahead of time")

    await _interaction(client, alice, planned["id"], datetime.now(UTC) + timedelta(days=3))
    await _interaction(
        client, alice, logged["id"], datetime.now(UTC) - timedelta(days=3), done=True
    )
    # Future but already marked as happened: nothing is left to happen.
    await _interaction(
        client, alice, ticked["id"], datetime.now(UTC) + timedelta(days=3), done=True
    )

    assert (await _read(client, alice, planned["id"]))["has_next_step"] is True
    assert (await _read(client, alice, logged["id"]))["has_next_step"] is False
    assert (await _read(client, alice, ticked["id"]))["has_next_step"] is False


async def test_the_list_carries_the_flag_too(client: AsyncClient, alice: Account) -> None:
    deal = await _deal(client, alice)
    await create_resource(client, alice, "/tasks/", {"title": "Call", "deal_id": deal["id"]})

    body = (await client.get("/deals/", headers=alice.headers)).json()

    assert [d["has_next_step"] for d in body["items"]] == [True]


# --- ?stalled=true -----------------------------------------------------------


async def test_stalled_lists_open_deals_with_nothing_next_longest_waiting_first(
    client: AsyncClient, alice: Account, bob: Account, session_factory: Sessions
) -> None:
    old = await _deal(client, alice, title="Old proposal", stage="proposal")
    fresh = await _deal(client, alice, title="Fresh lead")
    ancient = await _deal(client, alice, title="Ancient negotiation", stage="negotiation")
    tasked = await _deal(client, alice, title="Has a task", stage="proposal")
    await _deal(client, alice, title="Won, running", stage="running")
    await _deal(client, alice, title="Lost", stage="lost")
    # Nothing has been sent, so there is nothing to follow up on (#255).
    unsent = await _deal(client, alice, title="Unsent letter", stage="draft")
    await _deal(client, bob, title="Bob's quiet deal")

    await create_resource(client, alice, "/tasks/", {"title": "Call", "deal_id": tasked["id"]})
    await _age(session_factory, unsent, 200)
    await _age(session_factory, old, 30)
    await _age(session_factory, ancient, 90)
    await _age(session_factory, tasked, 120)

    response = await client.get("/deals/?stalled=true", headers=alice.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [d["title"] for d in body["items"]] == [
        ancient["title"],
        old["title"],
        fresh["title"],
    ]
    assert body["total"] == 3
    assert all(d["has_next_step"] is False for d in body["items"])


async def test_an_explicit_sort_overrides_the_stalled_default(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    later = await _deal(client, alice, title="Closes later", expected_close_date="2026-12-01")
    sooner = await _deal(client, alice, title="Closes sooner", expected_close_date="2026-11-01")
    await _age(session_factory, sooner, 30)
    await _age(session_factory, later, 60)

    response = await client.get(
        "/deals/?stalled=true&sort=expected_close_date", headers=alice.headers
    )

    assert [d["title"] for d in response.json()["items"]] == [sooner["title"], later["title"]]


async def test_without_stalled_the_list_is_unchanged(client: AsyncClient, alice: Account) -> None:
    deal = await _deal(client, alice)
    await create_resource(client, alice, "/tasks/", {"title": "Call", "deal_id": deal["id"]})
    await _deal(client, alice, title="Quiet")

    body = (await client.get("/deals/", headers=alice.headers)).json()

    assert body["total"] == 2
