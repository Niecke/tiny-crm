"""Tests for GET /tags (#290)."""

import json
from datetime import UTC, datetime

from httpx2 import AsyncClient

from tests.conftest import Account
from tests.test_cross_user_isolation import fake_object_store  # noqa: F401

NOW = datetime.now(UTC).isoformat()


async def test_tags_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/tags")
    assert response.status_code == 401


async def test_tags_empty(client: AsyncClient, alice: Account) -> None:
    response = await client.get("/tags", headers=alice.headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_tags_aggregates_and_deduplicates_across_models(
    client: AsyncClient, alice: Account
) -> None:
    # 1. Contact
    res = await client.post(
        "/contacts/",
        json={"name": "Alice Contact", "tags": ["partner", "client"]},
        headers=alice.headers,
    )
    assert res.status_code == 201

    # 2. Task
    res = await client.post(
        "/tasks/",
        json={"title": "Follow up task", "tags": ["client", "urgent"]},
        headers=alice.headers,
    )
    assert res.status_code == 201

    # 3. Interaction
    res = await client.post(
        "/interactions/",
        json={
            "kind": "note",
            "subject": "Initial chat",
            "occurred_at": NOW,
            "tags": ["followup", "urgent"],
        },
        headers=alice.headers,
    )
    assert res.status_code == 201

    # 4. Document
    res = await client.post(
        "/documents/",
        data={"title": "Spec", "tags": json.dumps(["contracts", "partner"])},
        files={"file": ("spec.txt", b"content", "text/plain")},
        headers=alice.headers,
    )
    assert res.status_code == 201

    # Check /tags and /tags/
    response = await client.get("/tags", headers=alice.headers)
    assert response.status_code == 200
    assert response.json() == ["client", "contracts", "followup", "partner", "urgent"]

    response_slash = await client.get("/tags/", headers=alice.headers)
    assert response_slash.status_code == 200
    assert response_slash.json() == response.json()


async def test_tags_excludes_archived_records(client: AsyncClient, alice: Account) -> None:
    # Create contact with archived tag and archive it
    contact_res = await client.post(
        "/contacts/",
        json={"name": "Archived Contact", "tags": ["archived-tag", "shared-tag"]},
        headers=alice.headers,
    )
    assert contact_res.status_code == 201
    contact_id = contact_res.json()["id"]

    archive_res = await client.post(f"/contacts/{contact_id}/archive", headers=alice.headers)
    assert archive_res.status_code == 200

    # An archived task is left out as well
    archived_task = await client.post(
        "/tasks/",
        json={"title": "Archived Task", "tags": ["archived-task-tag"]},
        headers=alice.headers,
    )
    assert archived_task.status_code == 201
    archive_res = await client.post(
        f"/tasks/{archived_task.json()['id']}/archive", headers=alice.headers
    )
    assert archive_res.status_code == 200

    # Create active task with active tag
    task_res = await client.post(
        "/tasks/",
        json={"title": "Active Task", "tags": ["active-tag"]},
        headers=alice.headers,
    )
    assert task_res.status_code == 201

    response = await client.get("/tags", headers=alice.headers)
    assert response.status_code == 200
    assert response.json() == ["active-tag"]


async def test_tags_user_isolation(client: AsyncClient, alice: Account, bob: Account) -> None:
    await client.post(
        "/contacts/",
        json={"name": "Alice Friend", "tags": ["alice-tag"]},
        headers=alice.headers,
    )
    await client.post(
        "/contacts/",
        json={"name": "Bob Friend", "tags": ["bob-tag"]},
        headers=bob.headers,
    )

    alice_res = await client.get("/tags", headers=alice.headers)
    assert alice_res.status_code == 200
    assert alice_res.json() == ["alice-tag"]

    bob_res = await client.get("/tags", headers=bob.headers)
    assert bob_res.status_code == 200
    assert bob_res.json() == ["bob-tag"]
