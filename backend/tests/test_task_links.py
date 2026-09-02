"""Tasks pointing at what they are about.

Tasks attached only to projects, so "call Maria back on Thursday" could not say
who Maria is. Three independent nullable FKs — contact, deal, interaction —
each validated against the caller's own rows, because the FK alone would accept
any existing id and reads carry the linked record's *name* back out.

The two details that are not plain CRUD: deleting a linked record keeps the
task (work you committed to does not vanish because a contact did), and a
recurring task carries its links onto the next instance (otherwise the series
detaches itself on the first completion).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx2 import AsyncClient

from tests.conftest import Account, create_resource

OCCURRED_AT = (datetime.now(UTC) - timedelta(days=1)).isoformat()


async def _contact(client: AsyncClient, account: Account, name: str = "Maria") -> dict[str, Any]:
    return await create_resource(client, account, "/contacts/", {"name": name})


async def _deal(client: AsyncClient, account: Account, title: str = "ACME work") -> dict[str, Any]:
    return await create_resource(client, account, "/deals/", {"title": title})


async def _interaction(
    client: AsyncClient, account: Account, subject: str = "Intro call"
) -> dict[str, Any]:
    return await create_resource(
        client, account, "/interactions/", {"subject": subject, "occurred_at": OCCURRED_AT}
    )


async def test_a_task_records_what_it_is_about(client: AsyncClient, alice: Account) -> None:
    contact = await _contact(client, alice, "Maria Rossi")
    deal = await _deal(client, alice, "Website relaunch")
    interaction = await _interaction(client, alice, "Kickoff call")

    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Call Maria back on Thursday",
            "contact_id": contact["id"],
            "deal_id": deal["id"],
            "interaction_id": interaction["id"],
        },
    )

    assert task["contact_id"] == contact["id"]
    assert task["deal_id"] == deal["id"]
    assert task["interaction_id"] == interaction["id"]
    # Denormalised, so a task list says what each one is about without a
    # request per row.
    assert task["contact_name"] == "Maria Rossi"
    assert task["deal_title"] == "Website relaunch"
    assert task["interaction_subject"] == "Kickoff call"

    listed = await client.get("/tasks/", headers=alice.headers)
    assert listed.json()["items"][0]["contact_name"] == "Maria Rossi"


async def test_a_plain_todo_links_to_nothing(client: AsyncClient, alice: Account) -> None:
    task = await create_resource(client, alice, "/tasks/", {"title": "Buy stamps"})

    for field in ("contact_id", "deal_id", "interaction_id"):
        assert task[field] is None
    for field in ("contact_name", "deal_title", "interaction_subject"):
        assert task[field] is None


async def test_the_three_links_are_independent(client: AsyncClient, alice: Account) -> None:
    # A task about a deal with no named contact yet is normal, and so is a
    # personal follow-up with no deal behind it.
    deal = await _deal(client, alice)
    only_deal = await create_resource(
        client, alice, "/tasks/", {"title": "Chase the tender", "deal_id": deal["id"]}
    )
    assert only_deal["deal_id"] == deal["id"]
    assert only_deal["contact_id"] is None

    contact = await _contact(client, alice)
    only_contact = await create_resource(
        client, alice, "/tasks/", {"title": "Birthday card", "contact_id": contact["id"]}
    )
    assert only_contact["contact_id"] == contact["id"]
    assert only_contact["deal_id"] is None


async def test_a_link_can_be_added_and_cleared_later(client: AsyncClient, alice: Account) -> None:
    contact = await _contact(client, alice, "Maria")
    task = await create_resource(client, alice, "/tasks/", {"title": "Follow up"})

    attached = await client.patch(
        f"/tasks/{task['id']}", json={"contact_id": contact["id"]}, headers=alice.headers
    )
    assert attached.status_code == 200
    assert attached.json()["contact_name"] == "Maria"

    detached = await client.patch(
        f"/tasks/{task['id']}", json={"contact_id": None}, headers=alice.headers
    )
    assert detached.status_code == 200
    assert detached.json()["contact_id"] is None
    assert detached.json()["contact_name"] is None


async def test_an_untouched_link_survives_an_unrelated_patch(
    client: AsyncClient, alice: Account
) -> None:
    # exclude_unset: a PATCH that never mentions the contact must not drop it.
    contact = await _contact(client, alice, "Maria")
    task = await create_resource(
        client, alice, "/tasks/", {"title": "Follow up", "contact_id": contact["id"]}
    )

    renamed = await client.patch(
        f"/tasks/{task['id']}", json={"title": "Follow up properly"}, headers=alice.headers
    )

    assert renamed.json()["contact_id"] == contact["id"]
    assert renamed.json()["contact_name"] == "Maria"


@pytest.mark.parametrize(
    ("field", "label"),
    [("contact_id", "Contact"), ("deal_id", "Deal"), ("interaction_id", "Interaction")],
)
async def test_an_unknown_link_target_is_refused(
    field: str, label: str, client: AsyncClient, alice: Account
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"

    created = await client.post(
        "/tasks/", json={"title": "X", field: missing}, headers=alice.headers
    )
    assert created.status_code == 404
    assert created.json()["detail"] == f"{label} not found"

    task = await create_resource(client, alice, "/tasks/", {"title": "X"})
    patched = await client.patch(
        f"/tasks/{task['id']}", json={field: missing}, headers=alice.headers
    )
    assert patched.status_code == 404


async def test_a_task_cannot_point_at_another_users_records(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    # The FK alone would accept these, and reads carry the linked record's name
    # back out — so this is a data leak, not just a tidiness check.
    alices = {
        "contact_id": (await _contact(client, alice, "Alice's contact"))["id"],
        "deal_id": (await _deal(client, alice, "Alice's deal"))["id"],
        "interaction_id": (await _interaction(client, alice, "Alice's call"))["id"],
    }

    for field, target_id in alices.items():
        response = await client.post(
            "/tasks/", json={"title": "Bob's task", field: target_id}, headers=bob.headers
        )
        assert response.status_code == 404, f"{field} should be refused"

    bobs_task = await create_resource(client, bob, "/tasks/", {"title": "Bob's task"})
    for field, target_id in alices.items():
        response = await client.patch(
            f"/tasks/{bobs_task['id']}", json={field: target_id}, headers=bob.headers
        )
        assert response.status_code == 404, f"{field} should be refused on patch"

    # And nothing leaked back on the read.
    read_back = await client.get(f"/tasks/{bobs_task['id']}", headers=bob.headers)
    assert read_back.json()["contact_name"] is None
    assert read_back.json()["deal_title"] is None
    assert read_back.json()["interaction_subject"] is None


async def test_tasks_can_be_listed_by_what_they_are_about(
    client: AsyncClient, alice: Account
) -> None:
    maria = await _contact(client, alice, "Maria")
    other = await _contact(client, alice, "Someone else")
    deal = await _deal(client, alice)
    interaction = await _interaction(client, alice)

    await create_resource(
        client, alice, "/tasks/", {"title": "Call Maria", "contact_id": maria["id"]}
    )
    await create_resource(
        client, alice, "/tasks/", {"title": "Email Maria", "contact_id": maria["id"]}
    )
    await create_resource(
        client, alice, "/tasks/", {"title": "Call the other one", "contact_id": other["id"]}
    )
    await create_resource(
        client, alice, "/tasks/", {"title": "Chase the deal", "deal_id": deal["id"]}
    )
    await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Send the deck", "interaction_id": interaction["id"]},
    )
    await create_resource(client, alice, "/tasks/", {"title": "Unattached"})

    # "What do I owe this person?" — the question that made T14 a P0.
    by_contact = await client.get(f"/tasks/?contact_id={maria['id']}", headers=alice.headers)
    assert by_contact.json()["total"] == 2
    assert {t["title"] for t in by_contact.json()["items"]} == {"Call Maria", "Email Maria"}

    by_deal = await client.get(f"/tasks/?deal_id={deal['id']}", headers=alice.headers)
    assert by_deal.json()["total"] == 1
    assert by_deal.json()["items"][0]["title"] == "Chase the deal"

    by_interaction = await client.get(
        f"/tasks/?interaction_id={interaction['id']}", headers=alice.headers
    )
    assert by_interaction.json()["total"] == 1
    assert by_interaction.json()["items"][0]["title"] == "Send the deck"

    # The unfiltered list is unchanged.
    assert (await client.get("/tasks/", headers=alice.headers)).json()["total"] == 6


async def test_the_filter_still_hides_done_tasks_unless_asked(
    client: AsyncClient, alice: Account
) -> None:
    maria = await _contact(client, alice, "Maria")
    done = await create_resource(
        client, alice, "/tasks/", {"title": "Called her", "contact_id": maria["id"]}
    )
    await client.patch(f"/tasks/{done['id']}", json={"done": True}, headers=alice.headers)
    await create_resource(
        client, alice, "/tasks/", {"title": "Still to call", "contact_id": maria["id"]}
    )

    open_only = await client.get(f"/tasks/?contact_id={maria['id']}", headers=alice.headers)
    assert open_only.json()["total"] == 1

    everything = await client.get(
        f"/tasks/?contact_id={maria['id']}&include_done=true", headers=alice.headers
    )
    assert everything.json()["total"] == 2


@pytest.mark.parametrize(
    ("field", "path"),
    [
        ("contact_id", "/contacts/"),
        ("deal_id", "/deals/"),
        ("interaction_id", "/interactions/"),
    ],
)
async def test_deleting_the_linked_record_keeps_the_task(
    field: str, path: str, client: AsyncClient, alice: Account
) -> None:
    targets = {
        "contact_id": _contact,
        "deal_id": _deal,
        "interaction_id": _interaction,
    }
    target = await targets[field](client, alice)
    task = await create_resource(
        client, alice, "/tasks/", {"title": "Work I promised", field: target["id"]}
    )

    assert (await client.delete(f"{path}{target['id']}", headers=alice.headers)).status_code == 204

    # Work the operator committed to does not vanish because the record it
    # pointed at did — the task survives, unattached.
    survivor = await client.get(f"/tasks/{task['id']}", headers=alice.headers)
    assert survivor.status_code == 200
    assert survivor.json()["title"] == "Work I promised"
    assert survivor.json()[field] is None


async def test_a_repeating_task_carries_its_links_to_the_next_instance(
    client: AsyncClient, alice: Account
) -> None:
    # "Check in with Maria monthly" must stay attached to Maria, or the series
    # detaches itself the first time it is completed.
    maria = await _contact(client, alice, "Maria")
    deal = await _deal(client, alice)
    due = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Check in with Maria",
            "due_date": due,
            "recurrence_rule": "monthly",
            "contact_id": maria["id"],
            "deal_id": deal["id"],
        },
    )

    completed = await client.patch(
        f"/tasks/{task['id']}", json={"done": True}, headers=alice.headers
    )

    assert completed.status_code == 200
    successor = completed.json()["next_occurrence"]
    assert successor is not None
    assert successor["contact_id"] == maria["id"]
    assert successor["contact_name"] == "Maria"
    assert successor["deal_id"] == deal["id"]
    assert successor["done"] is False
