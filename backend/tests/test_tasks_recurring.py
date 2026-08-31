"""Recurring tasks over the API: completion spawns the next instance."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


def in_days(days: int, hour: int = 23, minute: int = 59) -> str:
    moment = datetime.now(UTC) + timedelta(days=days)
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


async def complete(client: AsyncClient, account: Account, task_id: str) -> dict[str, Any]:
    response = await client.patch(f"/tasks/{task_id}", json={"done": True}, headers=account.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_completing_a_recurring_task_creates_the_next_one(
    client: AsyncClient, alice: Account
) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Check the ORF winners' job pages",
            "description": "Careers, then the press page.",
            "due_date": in_days(1),
            "priority": 1,
            "tags": ["research"],
            "recurrence_rule": "monthly",
        },
    )

    completed = await complete(client, alice, task["id"])

    successor = completed["next_occurrence"]
    assert successor is not None
    assert successor["title"] == task["title"]
    assert successor["description"] == task["description"]
    assert successor["priority"] == 1
    assert successor["tags"] == ["research"]
    assert successor["done"] is False
    assert successor["recurrence_rule"] == "monthly"
    assert successor["recurrence_parent_id"] == task["id"]

    due = datetime.fromisoformat(successor["due_date"])
    assert due.month == (datetime.fromisoformat(task["due_date"]).month % 12) + 1


async def test_the_completed_instance_survives_as_history(
    client: AsyncClient, alice: Account
) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Monthly check-in", "due_date": in_days(1), "recurrence_rule": "monthly"},
    )
    original_due = task["due_date"]

    await complete(client, alice, task["id"])

    stored = await client.get(f"/tasks/{task['id']}", headers=alice.headers)
    assert stored.status_code == 200
    # The row that was ticked off is untouched apart from `done` — its due date
    # is the answer to "did I actually check in March?".
    assert stored.json()["done"] is True
    assert stored.json()["due_date"] == original_due

    page = await client.get("/tasks/?include_done=true", headers=alice.headers)
    assert page.json()["total"] == 2


async def test_a_task_without_a_rule_spawns_nothing(client: AsyncClient, alice: Account) -> None:
    task = await create_resource(
        client, alice, "/tasks/", {"title": "One-off", "due_date": in_days(1)}
    )

    completed = await complete(client, alice, task["id"])

    assert completed["next_occurrence"] is None
    assert (await client.get("/tasks/?include_done=true", headers=alice.headers)).json()[
        "total"
    ] == 1


async def test_an_overdue_task_does_not_spawn_the_missed_slots(
    client: AsyncClient, alice: Account
) -> None:
    # Ninety days late on a weekly task: the next one is a week from *now*, not
    # a dozen backdated instances.
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Weekly review", "due_date": in_days(-90), "recurrence_rule": "weekly"},
    )

    completed = await complete(client, alice, task["id"])

    due = datetime.fromisoformat(completed["next_occurrence"]["due_date"])
    now = datetime.now(UTC)
    assert now < due <= now + timedelta(days=8)
    assert (await client.get("/tasks/?include_done=true", headers=alice.headers)).json()[
        "total"
    ] == 2


async def test_ticking_done_twice_does_not_fork_the_series(
    client: AsyncClient, alice: Account
) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Follow up with EBCONT", "due_date": in_days(1), "recurrence_rule": "weekly"},
    )
    await complete(client, alice, task["id"])

    undone = await client.patch(f"/tasks/{task['id']}", json={"done": False}, headers=alice.headers)
    assert undone.status_code == 200
    redone = await complete(client, alice, task["id"])

    assert redone["next_occurrence"] is None
    assert (await client.get("/tasks/?include_done=true", headers=alice.headers)).json()[
        "total"
    ] == 2


async def test_the_series_ends_at_recurrence_until(client: AsyncClient, alice: Account) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Weekly nudge until the deal closes",
            "due_date": in_days(1),
            "recurrence_rule": "weekly",
            "recurrence_until": in_days(5),
        },
    )

    completed = await complete(client, alice, task["id"])

    assert completed["next_occurrence"] is None
    assert (await client.get("/tasks/?include_done=true", headers=alice.headers)).json()[
        "total"
    ] == 1


async def test_the_interval_is_carried_into_the_next_instance(
    client: AsyncClient, alice: Account
) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Fortnightly follow-up",
            "due_date": in_days(1),
            "recurrence_rule": "weekly",
            "recurrence_interval": 2,
        },
    )

    successor = (await complete(client, alice, task["id"]))["next_occurrence"]

    assert successor["recurrence_interval"] == 2
    delta = datetime.fromisoformat(successor["due_date"]) - datetime.fromisoformat(task["due_date"])
    assert delta == timedelta(days=14)


async def test_the_next_instance_stays_in_the_same_projects(
    client: AsyncClient, alice: Account
) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Monthly report", "due_date": in_days(1), "recurrence_rule": "monthly"},
    )
    project = await create_resource(
        client,
        alice,
        "/projects/",
        {"name": "Retainer", "start_date": "2026-01-01", "task_ids": [task["id"]]},
    )

    successor = (await complete(client, alice, task["id"]))["next_occurrence"]

    linked = await client.get(f"/projects/{project['id']}", headers=alice.headers)
    assert set(linked.json()["task_ids"]) == {task["id"], successor["id"]}


async def test_a_recurring_task_needs_a_due_date(client: AsyncClient, alice: Account) -> None:
    rejected = await client.post(
        "/tasks/",
        json={"title": "Repeat from nothing", "recurrence_rule": "daily"},
        headers=alice.headers,
    )
    assert rejected.status_code == 422

    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Repeats", "due_date": in_days(1), "recurrence_rule": "daily"},
    )
    # Clearing the due date would leave the rule with nothing to repeat from.
    cleared = await client.patch(
        f"/tasks/{task['id']}", json={"due_date": None}, headers=alice.headers
    )
    assert cleared.status_code == 422
    assert "due date" in cleared.json()["detail"]


async def test_unusable_recurrence_settings_are_rejected(
    client: AsyncClient, alice: Account
) -> None:
    async def post(payload: dict[str, Any]) -> int:
        return (await client.post("/tasks/", json=payload, headers=alice.headers)).status_code

    assert (
        await post({"title": "Bad rule", "due_date": in_days(1), "recurrence_rule": "hourly"})
        == 422
    )
    assert (
        await post(
            {
                "title": "Zero interval",
                "due_date": in_days(1),
                "recurrence_rule": "daily",
                "recurrence_interval": 0,
            }
        )
        == 422
    )
    assert (
        await post(
            {"title": "End without a rule", "due_date": in_days(1), "recurrence_until": in_days(9)}
        )
        == 422
    )
    assert (
        await post(
            {
                "title": "Ends before it starts",
                "due_date": in_days(9),
                "recurrence_rule": "weekly",
                "recurrence_until": in_days(1),
            }
        )
        == 422
    )


async def test_recurrence_can_be_added_and_removed_by_patch(
    client: AsyncClient, alice: Account
) -> None:
    task = await create_resource(
        client, alice, "/tasks/", {"title": "Becomes a routine", "due_date": in_days(1)}
    )

    added = await client.patch(
        f"/tasks/{task['id']}",
        json={"recurrence_rule": "daily", "recurrence_interval": 3},
        headers=alice.headers,
    )
    assert added.status_code == 200
    assert added.json()["recurrence_rule"] == "daily"

    removed = await client.patch(
        f"/tasks/{task['id']}",
        json={"recurrence_rule": None, "recurrence_until": None},
        headers=alice.headers,
    )
    assert removed.status_code == 200
    assert removed.json()["recurrence_rule"] is None

    completed = await complete(client, alice, task["id"])
    assert completed["next_occurrence"] is None
