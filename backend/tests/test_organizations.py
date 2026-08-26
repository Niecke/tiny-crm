"""Organizations: CRUD, search, contact counts, and the link from a contact.

`Contact.company` was free text, so "ACME" and "Acme" were two companies and
nothing could be filed against the company itself. These tests pin the
replacement: an owned `Organization` row, a validated FK from the contact, and
the two questions the free-text column could never answer — everyone at a
company, and how many that is.
"""

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def test_an_organization_survives_a_full_round_trip(
    client: AsyncClient, alice: Account
) -> None:
    created = await create_resource(
        client,
        alice,
        "/organizations/",
        {
            "name": "ACME Corporation",
            "domain": "acme.example",
            # The shared mailbox and switchboard, not a person's own details.
            "email": "office@acme.example",
            "phone": "+49 30 123456",
            "address": "Hauptstraße 1, 10115 Berlin",
            "industry": "Manufacturing",
            "notes": "Pays on time.",
        },
    )
    assert created["email"] == "office@acme.example"
    assert created["phone"] == "+49 30 123456"
    assert created["contact_count"] == 0

    fetched = await client.get(f"/organizations/{created['id']}", headers=alice.headers)
    assert fetched.status_code == 200
    assert fetched.json()["domain"] == "acme.example"
    assert fetched.json()["industry"] == "Manufacturing"

    patched = await client.patch(
        f"/organizations/{created['id']}",
        json={"email": "info@acme.example"},
        headers=alice.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["email"] == "info@acme.example"
    assert patched.json()["name"] == "ACME Corporation"

    deleted = await client.delete(f"/organizations/{created['id']}", headers=alice.headers)
    assert deleted.status_code == 204
    assert (
        await client.get(f"/organizations/{created['id']}", headers=alice.headers)
    ).status_code == 404


async def test_the_list_reports_the_total_beyond_the_page(
    client: AsyncClient, alice: Account
) -> None:
    for index in range(5):
        await create_resource(client, alice, "/organizations/", {"name": f"Company {index}"})

    response = await client.get("/organizations/?limit=2", headers=alice.headers)

    assert response.status_code == 200
    page = response.json()
    assert len(page["items"]) == 2
    assert page["total"] == 5
    assert page["limit"] == 2


async def test_search_matches_the_name_or_the_domain(client: AsyncClient, alice: Account) -> None:
    await create_resource(
        client, alice, "/organizations/", {"name": "ACME Corporation", "domain": "acme.example"}
    )
    await create_resource(
        client, alice, "/organizations/", {"name": "Globex", "domain": "globex.example"}
    )

    by_name = await client.get("/organizations/?search=acme", headers=alice.headers)
    assert by_name.json()["total"] == 1
    assert by_name.json()["items"][0]["name"] == "ACME Corporation"

    # An email signature often gives the domain and nothing else.
    by_domain = await client.get("/organizations/?search=globex.ex", headers=alice.headers)
    assert by_domain.json()["total"] == 1
    assert by_domain.json()["items"][0]["name"] == "Globex"


async def test_an_organization_without_a_name_is_rejected(
    client: AsyncClient, alice: Account
) -> None:
    response = await client.post(
        "/organizations/", json={"domain": "acme.example"}, headers=alice.headers
    )

    assert response.status_code == 422


async def test_a_bad_page_size_is_rejected(client: AsyncClient, alice: Account) -> None:
    assert (await client.get("/organizations/?limit=0", headers=alice.headers)).status_code == 422
    assert (await client.get("/organizations/?limit=500", headers=alice.headers)).status_code == 422
    assert (await client.get("/organizations/?skip=-1", headers=alice.headers)).status_code == 422


async def test_a_contact_reads_back_its_organization_name(
    client: AsyncClient, alice: Account
) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "ACME"})

    contact = await create_resource(
        client,
        alice,
        "/contacts/",
        {"name": "Ada Lovelace", "organization_id": organization["id"]},
    )
    assert contact["organization_id"] == organization["id"]
    # Denormalised on read so a list needs no second request per row.
    assert contact["organization_name"] == "ACME"

    listed = await client.get("/contacts/", headers=alice.headers)
    assert listed.json()["items"][0]["organization_name"] == "ACME"


async def test_a_contact_can_be_moved_between_organizations_and_unlinked(
    client: AsyncClient, alice: Account
) -> None:
    acme = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    globex = await create_resource(client, alice, "/organizations/", {"name": "Globex"})
    contact = await create_resource(
        client, alice, "/contacts/", {"name": "Ada", "organization_id": acme["id"]}
    )

    moved = await client.patch(
        f"/contacts/{contact['id']}",
        json={"organization_id": globex["id"]},
        headers=alice.headers,
    )
    assert moved.status_code == 200
    assert moved.json()["organization_name"] == "Globex"

    unlinked = await client.patch(
        f"/contacts/{contact['id']}", json={"organization_id": None}, headers=alice.headers
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["organization_id"] is None
    assert unlinked.json()["organization_name"] is None


async def test_contacts_can_be_filtered_by_organization(
    client: AsyncClient, alice: Account
) -> None:
    acme = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    globex = await create_resource(client, alice, "/organizations/", {"name": "Globex"})
    await create_resource(
        client, alice, "/contacts/", {"name": "Ada", "organization_id": acme["id"]}
    )
    await create_resource(
        client, alice, "/contacts/", {"name": "Grace", "organization_id": acme["id"]}
    )
    await create_resource(
        client, alice, "/contacts/", {"name": "Alan", "organization_id": globex["id"]}
    )
    await create_resource(client, alice, "/contacts/", {"name": "Unaffiliated"})

    response = await client.get(f"/contacts/?organization_id={acme['id']}", headers=alice.headers)

    assert response.json()["total"] == 2
    assert [c["name"] for c in response.json()["items"]] == ["Ada", "Grace"]


async def test_the_contact_count_follows_the_links(client: AsyncClient, alice: Account) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    contact = await create_resource(
        client, alice, "/contacts/", {"name": "Ada", "organization_id": organization["id"]}
    )
    await create_resource(
        client, alice, "/contacts/", {"name": "Grace", "organization_id": organization["id"]}
    )

    detail = await client.get(f"/organizations/{organization['id']}", headers=alice.headers)
    assert detail.json()["contact_count"] == 2
    listed = await client.get("/organizations/", headers=alice.headers)
    assert listed.json()["items"][0]["contact_count"] == 2

    await client.delete(f"/contacts/{contact['id']}", headers=alice.headers)

    after = await client.get(f"/organizations/{organization['id']}", headers=alice.headers)
    assert after.json()["contact_count"] == 1


async def test_deleting_an_organization_keeps_its_contacts(
    client: AsyncClient, alice: Account
) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    contact = await create_resource(
        client, alice, "/contacts/", {"name": "Ada", "organization_id": organization["id"]}
    )

    assert (
        await client.delete(f"/organizations/{organization['id']}", headers=alice.headers)
    ).status_code == 204

    # The company is gone; the person we know there is not.
    survivor = await client.get(f"/contacts/{contact['id']}", headers=alice.headers)
    assert survivor.status_code == 200
    assert survivor.json()["organization_id"] is None
    assert survivor.json()["organization_name"] is None


async def test_an_unknown_organization_is_refused_on_a_contact(
    client: AsyncClient, alice: Account
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"

    created = await client.post(
        "/contacts/",
        json={"name": "Ada", "organization_id": missing},
        headers=alice.headers,
    )
    assert created.status_code == 404

    contact = await create_resource(client, alice, "/contacts/", {"name": "Grace"})
    patched = await client.patch(
        f"/contacts/{contact['id']}",
        json={"organization_id": missing},
        headers=alice.headers,
    )
    assert patched.status_code == 404


async def test_a_contact_cannot_be_filed_under_another_users_organization(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    alices_company = await create_resource(client, alice, "/organizations/", {"name": "ACME"})

    created = await client.post(
        "/contacts/",
        json={"name": "Bob's contact", "organization_id": alices_company["id"]},
        headers=bob.headers,
    )
    assert created.status_code == 404

    bobs_contact = await create_resource(client, bob, "/contacts/", {"name": "Bob's contact"})
    patched = await client.patch(
        f"/contacts/{bobs_contact['id']}",
        json={"organization_id": alices_company["id"]},
        headers=bob.headers,
    )
    assert patched.status_code == 404
    # And nothing leaked back: Bob's contact still has no company.
    assert (await client.get(f"/contacts/{bobs_contact['id']}", headers=bob.headers)).json()[
        "organization_name"
    ] is None
