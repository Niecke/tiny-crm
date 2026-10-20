"""Interactions: CRUD, the past/planned split and contact links."""

from datetime import UTC, datetime, timedelta

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource, erase

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

    assert (await erase(client, alice, f"/interactions/{created['id']}")).status_code == 204


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


async def test_filtering_by_date_range_after_and_before(
    client: AsyncClient, alice: Account
) -> None:
    for subject, day in (("Early", 1), ("Middle", 10), ("Late", 20)):
        await create_resource(
            client,
            alice,
            "/interactions/",
            {"subject": subject, "occurred_at": f"2030-03-{day:02d}T12:00:00+00:00"},
        )

    async def subjects(query: str) -> set[str]:
        response = await client.get(f"/interactions/?{query}", headers=alice.headers)
        assert response.status_code == 200
        return {i["subject"] for i in response.json()["items"]}

    assert await subjects("occurred_after=2030-03-05T00:00:00Z") == {"Middle", "Late"}
    assert await subjects("occurred_before=2030-03-15T00:00:00Z") == {"Early", "Middle"}
    assert await subjects(
        "occurred_after=2030-03-05T00:00:00Z&occurred_before=2030-03-15T00:00:00Z"
    ) == {"Middle"}
    # Both bounds are inclusive.
    assert await subjects(
        "occurred_after=2030-03-10T12:00:00Z&occurred_before=2030-03-10T12:00:00Z"
    ) == {"Middle"}


async def test_date_range_bounds_must_be_timezone_aware_and_ordered(
    client: AsyncClient, alice: Account
) -> None:
    naive = await client.get(
        "/interactions/?occurred_after=2030-03-05T00:00:00", headers=alice.headers
    )
    assert naive.status_code == 422
    reversed_range = await client.get(
        "/interactions/?occurred_after=2030-03-15T00:00:00Z&occurred_before=2030-03-05T00:00:00Z",
        headers=alice.headers,
    )
    assert reversed_range.status_code == 422


async def test_date_range_queries_isolate_users(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Alice's", "occurred_at": "2030-03-10T12:00:00+00:00"},
    )
    await create_resource(
        client,
        bob,
        "/interactions/",
        {"subject": "Bob's", "occurred_at": "2030-03-11T12:00:00+00:00"},
    )

    response = await client.get(
        "/interactions/?occurred_after=2030-03-01T00:00:00Z&occurred_before=2030-03-31T00:00:00Z",
        headers=alice.headers,
    )
    assert [i["subject"] for i in response.json()["items"]] == ["Alice's"]


async def test_an_event_is_a_kind_of_its_own(client: AsyncClient, alice: Account) -> None:
    # A conference or meetup: the people met there go on as contacts, so an
    # event needs no entity of its own — only a kind the filter can find.
    contact = await create_resource(client, alice, "/contacts/", {"name": "Grace Hopper"})
    await create_resource(
        client,
        alice,
        "/interactions/",
        {
            "subject": "DevOpsCon",
            "kind": "event",
            "occurred_at": PAST,
            "contact_ids": [contact["id"]],
        },
    )
    await create_resource(client, alice, "/interactions/", {"subject": "Call", "occurred_at": PAST})

    by_kind = await client.get("/interactions/?kind=event", headers=alice.headers)
    [event] = by_kind.json()["items"]
    assert (event["subject"], event["contact_ids"]) == ("DevOpsCon", [contact["id"]])


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
