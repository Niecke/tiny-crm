"""Contacts: full CRUD round-trip, list paging and input validation."""

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def test_a_contact_survives_a_full_round_trip(client: AsyncClient, alice: Account) -> None:
    created = await create_resource(
        client,
        alice,
        "/contacts/",
        {"name": "Ada Lovelace", "email": "ada@example.com", "tags": ["vip"]},
    )

    fetched = await client.get(f"/contacts/{created['id']}", headers=alice.headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Ada Lovelace"
    assert fetched.json()["tags"] == ["vip"]

    patched = await client.patch(
        f"/contacts/{created['id']}",
        json={"email": "ada@somerset.example"},
        headers=alice.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["email"] == "ada@somerset.example"
    assert patched.json()["name"] == "Ada Lovelace"

    deleted = await client.delete(f"/contacts/{created['id']}", headers=alice.headers)
    assert deleted.status_code == 204

    gone = await client.get(f"/contacts/{created['id']}", headers=alice.headers)
    assert gone.status_code == 404


async def test_the_list_reports_the_total_beyond_the_page(
    client: AsyncClient, alice: Account
) -> None:
    for index in range(5):
        await create_resource(client, alice, "/contacts/", {"name": f"Contact {index}"})

    response = await client.get("/contacts/?limit=2", headers=alice.headers)

    assert response.status_code == 200
    page = response.json()
    assert len(page["items"]) == 2
    assert page["total"] == 5
    assert page["limit"] == 2


async def test_search_filters_by_name(client: AsyncClient, alice: Account) -> None:
    await create_resource(client, alice, "/contacts/", {"name": "Grace Hopper"})
    await create_resource(client, alice, "/contacts/", {"name": "Ada Lovelace"})

    response = await client.get("/contacts/?search=hopper", headers=alice.headers)

    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Grace Hopper"


async def test_a_contact_without_a_name_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/contacts/", json={"email": "nameless@example.com"}, headers=alice.headers
    )

    assert response.status_code == 422


async def test_a_bad_page_size_is_rejected(client: AsyncClient, alice: Account) -> None:
    assert (await client.get("/contacts/?limit=0", headers=alice.headers)).status_code == 422
    assert (await client.get("/contacts/?limit=500", headers=alice.headers)).status_code == 422
    assert (await client.get("/contacts/?skip=-1", headers=alice.headers)).status_code == 422
