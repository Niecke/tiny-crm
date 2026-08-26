"""Tasks: CRUD, the done filter and due-date handling."""

from httpx import AsyncClient

from tests.conftest import Account, create_resource


async def test_a_task_survives_a_full_round_trip(client: AsyncClient, alice: Account) -> None:
    created = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Call the accountant",
            "due_date": "2026-09-01T09:00:00Z",
            "priority": 2,
            "tags": ["finance"],
        },
    )

    fetched = await client.get(f"/tasks/{created['id']}", headers=alice.headers)
    assert fetched.status_code == 200
    assert fetched.json()["priority"] == 2
    assert fetched.json()["due_date"].startswith("2026-09-01T09:00:00")

    patched = await client.patch(
        f"/tasks/{created['id']}", json={"done": True}, headers=alice.headers
    )
    assert patched.status_code == 200
    assert patched.json()["done"] is True

    assert (
        await client.delete(f"/tasks/{created['id']}", headers=alice.headers)
    ).status_code == 204
    assert (await client.get(f"/tasks/{created['id']}", headers=alice.headers)).status_code == 404


async def test_done_tasks_are_hidden_unless_asked_for(client: AsyncClient, alice: Account) -> None:
    open_task = await create_resource(client, alice, "/tasks/", {"title": "Still open"})
    done_task = await create_resource(client, alice, "/tasks/", {"title": "Finished"})
    await client.patch(f"/tasks/{done_task['id']}", json={"done": True}, headers=alice.headers)

    default_page = await client.get("/tasks/", headers=alice.headers)
    assert [t["id"] for t in default_page.json()["items"]] == [open_task["id"]]

    with_done = await client.get("/tasks/?include_done=true", headers=alice.headers)
    assert with_done.json()["total"] == 2


async def test_tasks_without_a_due_date_sort_last(client: AsyncClient, alice: Account) -> None:
    await create_resource(client, alice, "/tasks/", {"title": "Someday"})
    await create_resource(
        client, alice, "/tasks/", {"title": "Tomorrow", "due_date": "2026-08-27T08:00:00Z"}
    )

    items = (await client.get("/tasks/", headers=alice.headers)).json()["items"]

    assert [t["title"] for t in items] == ["Tomorrow", "Someday"]


async def test_a_task_without_a_title_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post("/tasks/", json={"priority": 1}, headers=alice.headers)

    assert response.status_code == 422
