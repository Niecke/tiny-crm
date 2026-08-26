"""Every router re-implements the same `user_id` ownership check by hand, so
one missed comparison leaks another tenant's data. These tests walk all five
owned resources through the same script: Alice creates a row, Bob must not be
able to read, change, delete or even see it, and an anonymous caller gets 401.

New router? Add it to RESOURCES and it is covered.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

import pytest
from httpx2 import AsyncClient

from app.routers import documents
from tests.conftest import Account, create_resource

OCCURRED_AT = (datetime.now(UTC) - timedelta(days=1)).isoformat()

Creator = Callable[[AsyncClient, Account], Awaitable[dict[str, Any]]]


@pytest.fixture(autouse=True)
def fake_object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Documents are one of the resources under test; S3 is not."""
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


async def _create_document(client: AsyncClient, account: Account) -> dict[str, Any]:
    response = await client.post(
        "/documents/",
        data={"title": "Private notes", "tags": "[]"},
        files={"file": ("notes.txt", b"private\n", "text/plain")},
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _json_creator(path: str, payload: dict[str, Any]) -> Creator:
    async def create(client: AsyncClient, account: Account) -> dict[str, Any]:
        return await create_resource(client, account, path, payload)

    return create


@dataclass
class Resource:
    name: str
    path: str
    create: Creator
    update: dict[str, Any]


RESOURCES = [
    Resource(
        "contacts",
        "/contacts/",
        _json_creator("/contacts/", {"name": "Ada Lovelace"}),
        {"name": "Renamed by Bob"},
    ),
    Resource(
        "tasks",
        "/tasks/",
        _json_creator("/tasks/", {"title": "Alice's task"}),
        {"title": "Renamed by Bob"},
    ),
    Resource(
        "projects",
        "/projects/",
        _json_creator("/projects/", {"name": "Alice's project", "start_date": "2026-08-01"}),
        {"name": "Renamed by Bob"},
    ),
    Resource(
        "interactions",
        "/interactions/",
        _json_creator("/interactions/", {"subject": "Alice's call", "occurred_at": OCCURRED_AT}),
        {"subject": "Renamed by Bob"},
    ),
    Resource("documents", "/documents/", _create_document, {"title": "Renamed by Bob"}),
]

RESOURCE_IDS = [resource.name for resource in RESOURCES]


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_another_user_cannot_read_the_row(
    resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    row = await resource.create(client, alice)

    response = await client.get(f"{resource.path}{row['id']}", headers=bob.headers)

    assert response.status_code == 404


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_another_user_cannot_change_the_row(
    resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    row = await resource.create(client, alice)

    response = await client.patch(
        f"{resource.path}{row['id']}", json=resource.update, headers=bob.headers
    )

    assert response.status_code == 404
    # And the row is untouched.
    still_there = await client.get(f"{resource.path}{row['id']}", headers=alice.headers)
    assert still_there.status_code == 200
    for field, value in resource.update.items():
        assert still_there.json()[field] != value


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_another_user_cannot_delete_the_row(
    resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    row = await resource.create(client, alice)

    response = await client.delete(f"{resource.path}{row['id']}", headers=bob.headers)

    assert response.status_code == 404
    assert (
        await client.get(f"{resource.path}{row['id']}", headers=alice.headers)
    ).status_code == 200


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_another_users_rows_are_not_listed(
    resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    await resource.create(client, alice)

    response = await client.get(resource.path, headers=bob.headers)

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_every_route_requires_a_token(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)

    assert (await client.get(resource.path)).status_code == 401
    assert (await client.get(f"{resource.path}{row['id']}")).status_code == 401
    assert (
        await client.patch(f"{resource.path}{row['id']}", json=resource.update)
    ).status_code == 401
    assert (await client.delete(f"{resource.path}{row['id']}")).status_code == 401


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_an_unknown_id_is_a_404_for_its_owner_too(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"

    assert (await client.get(f"{resource.path}{missing}", headers=alice.headers)).status_code == 404


async def test_document_content_and_preview_are_owner_only(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    document = await _create_document(client, alice)

    assert (
        await client.get(f"/documents/{document['id']}/content", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.get(f"/documents/{document['id']}/preview", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.put(
            f"/documents/{document['id']}/content",
            files={"file": ("evil.txt", b"overwritten\n", "text/plain")},
            headers=bob.headers,
        )
    ).status_code == 404
