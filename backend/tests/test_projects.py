"""Projects: CRUD plus the link lists that fan out to other tables."""

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def test_a_project_survives_a_full_round_trip(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada Lovelace"})
    task = await create_resource(client, alice, "/tasks/", {"title": "Draft the proposal"})

    created = await create_resource(
        client,
        alice,
        "/projects/",
        {
            "name": "Engine overhaul",
            "start_date": "2026-08-01",
            "contact_ids": [contact["id"]],
            "task_ids": [task["id"]],
        },
    )

    assert created["contact_ids"] == [contact["id"]]
    assert created["task_ids"] == [task["id"]]

    patched = await client.patch(
        f"/projects/{created['id']}",
        json={"end_date": "2026-12-31", "task_ids": []},
        headers=alice.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["end_date"] == "2026-12-31"
    assert patched.json()["task_ids"] == []
    # Unlinking a task must not delete it.
    assert (await client.get(f"/tasks/{task['id']}", headers=alice.headers)).status_code == 200

    assert (
        await client.delete(f"/projects/{created['id']}", headers=alice.headers)
    ).status_code == 204
    assert (
        await client.get(f"/contacts/{contact['id']}", headers=alice.headers)
    ).status_code == 200


async def test_a_project_needs_a_name_and_a_start_date(client: AsyncClient, alice: Account) -> None:
    assert (
        await client.post("/projects/", json={"name": "No date"}, headers=alice.headers)
    ).status_code == 422
    assert (
        await client.post("/projects/", json={"start_date": "2026-08-01"}, headers=alice.headers)
    ).status_code == 422


async def test_linking_another_users_rows_is_refused(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    bobs_task = await create_resource(client, bob, "/tasks/", {"title": "Bob's task"})

    response = await client.post(
        "/projects/",
        json={
            "name": "Borrowed work",
            "start_date": "2026-08-01",
            "task_ids": [bobs_task["id"]],
        },
        headers=alice.headers,
    )

    assert response.status_code == 404
