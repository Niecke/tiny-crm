"""Tests for the unified contact timeline (T15, #130).

Verifies merging interactions, tasks, deals, documents and audit changes into a
single reverse-chronological feed with filtering, pagination and tenant isolation.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

import pytest
from httpx2 import AsyncClient

from app.routers import documents
from tests.conftest import Account, create_resource


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, bytes]]:
    store: dict[str, bytes] = {}

    async def put_object(key: str, data: bytes, content_type: str) -> None:
        store[key] = bytes(data)

    async def put_object_stream(key: str, fileobj: BinaryIO, content_type: str) -> None:
        fileobj.seek(0)
        store[key] = fileobj.read()

    async def get_object_stream(key: str) -> AsyncIterator[bytes]:
        yield store[key]

    async def delete_object(key: str) -> None:
        store.pop(key, None)

    monkeypatch.setattr(documents, "put_object", put_object)
    monkeypatch.setattr(documents, "put_object_stream", put_object_stream)
    monkeypatch.setattr(documents, "get_object_stream", get_object_stream)
    monkeypatch.setattr(documents, "delete_object", delete_object)
    yield store


async def test_timeline_merges_all_five_entity_types_in_order(
    client: AsyncClient, alice: Account, fake_storage: dict[str, bytes]
) -> None:
    # 1. Contact
    contact = await create_resource(
        client,
        alice,
        "/contacts/",
        {"name": "Ada Lovelace", "email": "ada@example.com"},
    )
    contact_id = contact["id"]

    now = datetime.now(UTC)

    # 2. Interaction
    occurred = (now - timedelta(days=2)).isoformat()
    await create_resource(
        client,
        alice,
        "/interactions/",
        {
            "kind": "call",
            "subject": "Introductory Discovery Call",
            "occurred_at": occurred,
            "contact_ids": [contact_id],
        },
    )

    # 3. Task
    due = (now - timedelta(days=1)).isoformat()
    await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Send proposal deck",
            "due_date": due,
            "contact_id": contact_id,
        },
    )

    # 4. Deal
    await create_resource(
        client,
        alice,
        "/deals/",
        {
            "title": "Architecture Consulting Deal",
            "stage": "lead",
            "contact_id": contact_id,
            "value_type": "fixed",
            "fixed_value": 15000,
        },
    )

    # 5. Document
    files = {"file": ("contract.pdf", b"%PDF-1.4 mock", "application/pdf")}
    data = {
        "title": "Master Services Agreement",
        "contact_ids": f'["{contact_id}"]',
    }
    doc_res = await client.post("/documents/", data=data, files=files, headers=alice.headers)
    assert doc_res.status_code == 201

    # 6. Audit Event (patch contact)
    patch_res = await client.patch(
        f"/contacts/{contact_id}",
        json={"notes": "Key technical decision maker"},
        headers=alice.headers,
    )
    assert patch_res.status_code == 200

    # Fetch unified timeline
    res = await client.get(f"/contacts/{contact_id}/timeline", headers=alice.headers)
    assert res.status_code == 200
    timeline = res.json()

    assert timeline["total"] == 5
    items = timeline["items"]
    assert len(items) == 5

    types_found = {item["item_type"] for item in items}
    assert types_found == {"interaction", "task", "deal", "document", "change"}

    # Timestamps must be sorted in descending order
    timestamps = [datetime.fromisoformat(item["timestamp"]) for item in items]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_timeline_filtering_by_types(
    client: AsyncClient, alice: Account, fake_storage: dict[str, bytes]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Grace Hopper"})
    contact_id = contact["id"]

    now = datetime.now(UTC).isoformat()
    await create_resource(
        client,
        alice,
        "/interactions/",
        {"kind": "email", "subject": "Email sent", "occurred_at": now, "contact_ids": [contact_id]},
    )
    await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Follow-up", "contact_id": contact_id},
    )

    # Filter for only interactions
    res = await client.get(
        f"/contacts/{contact_id}/timeline?types=interaction", headers=alice.headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["item_type"] == "interaction"

    # Filter for multiple types (multi-param)
    res_multi = await client.get(
        f"/contacts/{contact_id}/timeline?types=interaction&types=task", headers=alice.headers
    )
    assert res_multi.status_code == 200
    assert res_multi.json()["total"] == 2


async def test_timeline_pagination(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Alan Turing"})
    contact_id = contact["id"]

    for i in range(5):
        now = (datetime.now(UTC) - timedelta(hours=i)).isoformat()
        await create_resource(
            client,
            alice,
            "/interactions/",
            {
                "kind": "note",
                "subject": f"Note {i}",
                "occurred_at": now,
                "contact_ids": [contact_id],
            },
        )

    res_p1 = await client.get(
        f"/contacts/{contact_id}/timeline?limit=2&skip=0", headers=alice.headers
    )
    assert res_p1.status_code == 200
    p1 = res_p1.json()
    assert p1["total"] == 5
    assert len(p1["items"]) == 2
    assert p1["items"][0]["title"] == "Note 0"

    res_p2 = await client.get(
        f"/contacts/{contact_id}/timeline?limit=2&skip=2", headers=alice.headers
    )
    assert res_p2.status_code == 200
    p2 = res_p2.json()
    assert len(p2["items"]) == 2
    assert p2["items"][0]["title"] == "Note 2"


async def test_timeline_multi_tenant_isolation(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Secret VIP"})
    contact_id = contact["id"]

    # Bob cannot access Alice's contact timeline
    bob_res = await client.get(f"/contacts/{contact_id}/timeline", headers=bob.headers)
    assert bob_res.status_code == 404


async def test_timeline_archived_filter(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Test Archive"})
    contact_id = contact["id"]

    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Archived Task", "contact_id": contact_id},
    )
    # Archive the task
    arc_res = await client.post(f"/tasks/{task['id']}/archive", headers=alice.headers)
    assert arc_res.status_code == 200

    # By default (archived=False), task is not returned
    live_res = await client.get(
        f"/contacts/{contact_id}/timeline?types=task", headers=alice.headers
    )
    assert live_res.status_code == 200
    assert live_res.json()["total"] == 0

    # With archived=True, task is returned
    arc_res = await client.get(
        f"/contacts/{contact_id}/timeline?types=task&archived=true", headers=alice.headers
    )
    assert arc_res.status_code == 200
    assert arc_res.json()["total"] == 1
