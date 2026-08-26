"""Interactions: CRUD, the past/planned split and contact links."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import Account, create_resource

PAST = (datetime.now(UTC) - timedelta(days=2)).isoformat()
FUTURE = (datetime.now(UTC) + timedelta(days=2)).isoformat()


async def test_an_interaction_survives_a_full_round_trip(
    client: AsyncClient, alice: Account
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada Lovelace"})
    created = await create_resource(
        client,
        alice,
        "/interactions/",
        {
            "kind": "call",
            "subject": "Kickoff call",
            "occurred_at": PAST,
            "duration_minutes": 30,
            "done": True,
            "contact_ids": [contact["id"]],
        },
    )

    assert created["contact_ids"] == [contact["id"]]

    patched = await client.patch(
        f"/interactions/{created['id']}",
        json={"subject": "Kickoff call (rescheduled)", "contact_ids": []},
        headers=alice.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["subject"] == "Kickoff call (rescheduled)"
    assert patched.json()["contact_ids"] == []

    assert (
        await client.delete(f"/interactions/{created['id']}", headers=alice.headers)
    ).status_code == 204


async def test_upcoming_and_past_are_separate_views(client: AsyncClient, alice: Account) -> None:
    await create_resource(
        client, alice, "/interactions/", {"subject": "Logged", "occurred_at": PAST}
    )
    await create_resource(
        client, alice, "/interactions/", {"subject": "Planned", "occurred_at": FUTURE}
    )

    upcoming = await client.get("/interactions/?upcoming=true", headers=alice.headers)
    assert [i["subject"] for i in upcoming.json()["items"]] == ["Planned"]

    past = await client.get("/interactions/?upcoming=false", headers=alice.headers)
    assert [i["subject"] for i in past.json()["items"]] == ["Logged"]

    everything = await client.get("/interactions/", headers=alice.headers)
    assert everything.json()["total"] == 2


async def test_filtering_by_contact_and_kind(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Grace Hopper"})
    await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Linked", "occurred_at": PAST, "contact_ids": [contact["id"]]},
    )
    await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Unlinked", "kind": "email", "occurred_at": PAST},
    )

    by_contact = await client.get(
        f"/interactions/?contact_id={contact['id']}", headers=alice.headers
    )
    assert [i["subject"] for i in by_contact.json()["items"]] == ["Linked"]

    by_kind = await client.get("/interactions/?kind=email", headers=alice.headers)
    assert [i["subject"] for i in by_kind.json()["items"]] == ["Unlinked"]


async def test_an_unknown_kind_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/interactions/",
        json={"kind": "carrier-pigeon", "subject": "Nope", "occurred_at": PAST},
        headers=alice.headers,
    )

    assert response.status_code == 422


async def test_linking_a_contact_of_another_user_is_refused(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    bobs_contact = await create_resource(client, bob, "/contacts/", {"name": "Bob's client"})

    response = await client.post(
        "/interactions/",
        json={
            "subject": "Poaching attempt",
            "occurred_at": PAST,
            "contact_ids": [bobs_contact["id"]],
        },
        headers=alice.headers,
    )

    assert response.status_code == 404
