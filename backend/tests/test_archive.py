"""Archive instead of delete (#140), through the API.

The first half walks every record type through the same script — archive it,
find it gone from the list and still there by its id, restore it, and only then
be allowed to delete it. The second half is what archiving means for each kind
of record in particular: a contact's history keeps naming them, a deal leaves
the numbers, a capture still has its Undo.

New router? It is in RESOURCES already if tests/test_cross_user_isolation.py
knows about it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx2 import AsyncClient

from tests.conftest import Account, create_resource, erase

# The fixture is imported for its side effect: documents are one of the
# resources under test here too, and S3 is not.
from tests.test_cross_user_isolation import (  # noqa: F401
    RESOURCE_IDS,
    RESOURCES,
    Resource,
    fake_object_store,
)

YESTERDAY = (datetime.now(UTC) - timedelta(days=1)).isoformat()
TOMORROW = (datetime.now(UTC) + timedelta(days=1)).isoformat()

# Every list defaults to something narrower than "all of them"; these widen it
# so a row is missing from a list only because it was archived.
EVERYTHING: dict[str, dict[str, str]] = {
    "captures": {"status": "all"},
    "tasks": {"include_done": "true"},
}


async def _ids(
    client: AsyncClient, account: Account, resource: Resource, **params: str
) -> list[str]:
    response = await client.get(
        resource.path,
        params={**EVERYTHING.get(resource.name, {}), **params},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def _post(client: AsyncClient, account: Account, path: str) -> dict[str, Any]:
    response = await client.post(path, headers=account.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _get(client: AsyncClient, account: Account, path: str) -> dict[str, Any]:
    response = await client.get(path, headers=account.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- The same script for every record type -----------------------------------


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_an_archived_row_leaves_the_list_and_comes_back(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    assert row["archived_at"] is None
    path = f"{resource.path}{row['id']}"

    archived = await _post(client, alice, f"{path}/archive")

    assert archived["archived_at"] is not None
    assert await _ids(client, alice, resource) == []
    # The archive is its own list, never mixed into the other one.
    assert await _ids(client, alice, resource, archived="true") == [row["id"]]
    # Still there by its id: whatever links to it has to keep resolving.
    assert (await _get(client, alice, path))["archived_at"] is not None

    restored = await _post(client, alice, f"{path}/restore")

    assert restored["archived_at"] is None
    assert await _ids(client, alice, resource) == [row["id"]]
    assert await _ids(client, alice, resource, archived="true") == []


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_archiving_twice_keeps_the_first_date(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    path = f"{resource.path}{row['id']}"

    first = await _post(client, alice, f"{path}/archive")
    second = await _post(client, alice, f"{path}/archive")

    # When it was put away, not when the button was last pressed.
    assert second["archived_at"] == first["archived_at"]


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_restoring_a_row_that_was_never_archived_changes_nothing(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)

    restored = await _post(client, alice, f"{resource.path}{row['id']}/restore")

    assert restored["archived_at"] is None
    assert await _ids(client, alice, resource) == [row["id"]]


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_an_archived_row_cannot_be_changed(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    path = f"{resource.path}{row['id']}"
    await _post(client, alice, f"{path}/archive")

    response = await client.patch(path, json=resource.update, headers=alice.headers)

    assert response.status_code == 409
    assert "archived" in response.json()["detail"]
    unchanged = await _get(client, alice, path)
    for field, value in resource.update.items():
        assert unchanged[field] != value


@pytest.mark.parametrize(
    "resource",
    # A capture nobody has worked yet is the one exception; see below.
    [r for r in RESOURCES if r.name != "captures"],
    ids=[name for name in RESOURCE_IDS if name != "captures"],
)
async def test_a_row_is_only_deleted_once_it_was_archived(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    path = f"{resource.path}{row['id']}"

    refused = await client.delete(path, headers=alice.headers)

    assert refused.status_code == 409
    assert "archive it" in refused.json()["detail"]
    assert (await client.get(path, headers=alice.headers)).status_code == 200

    assert (await erase(client, alice, path)).status_code == 204
    assert (await client.get(path, headers=alice.headers)).status_code == 404


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
@pytest.mark.parametrize("action", ["archive", "restore"])
async def test_another_user_cannot_archive_or_restore_the_row(
    action: str, resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    row = await resource.create(client, alice)
    path = f"{resource.path}{row['id']}"
    if action == "restore":
        await _post(client, alice, f"{path}/archive")

    response = await client.post(f"{path}/{action}", headers=bob.headers)

    assert response.status_code == 404
    # And the row is as Alice left it.
    still = await _get(client, alice, path)
    assert (still["archived_at"] is not None) == (action == "restore")


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_archiving_requires_a_token(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    path = f"{resource.path}{row['id']}"

    assert (await client.post(f"{path}/archive")).status_code == 401
    assert (await client.post(f"{path}/restore")).status_code == 401


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_another_users_archive_is_not_listed(
    resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    row = await resource.create(client, alice)
    await _post(client, alice, f"{resource.path}{row['id']}/archive")

    assert await _ids(client, bob, resource, archived="true") == []


async def test_search_does_not_find_what_was_archived(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Grace Hopper"})
    task = await create_resource(client, alice, "/tasks/", {"title": "Write to Grace Hopper"})

    async def hits() -> dict[str, int]:
        found = await _get(client, alice, "/search/?q=hopper")
        return {group["type"]: group["total"] for group in found["groups"]}

    assert (await hits())["contacts"] == 1
    assert (await hits())["tasks"] == 1

    await _post(client, alice, f"/contacts/{contact['id']}/archive")
    await _post(client, alice, f"/tasks/{task['id']}/archive")

    assert (await hits())["contacts"] == 0
    assert (await hits())["tasks"] == 0

    await _post(client, alice, f"/contacts/{contact['id']}/restore")

    assert (await hits())["contacts"] == 1


# --- Contacts and organizations: the trail survives --------------------------


async def test_history_keeps_naming_an_archived_contact(
    client: AsyncClient, alice: Account
) -> None:
    """The whole point (#140): a delete leaves the call with nobody on it."""
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada Lovelace"})
    interaction = await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Intro call", "occurred_at": YESTERDAY, "contact_ids": [contact["id"]]},
    )
    task = await create_resource(
        client, alice, "/tasks/", {"title": "Send the deck", "contact_id": contact["id"]}
    )
    deal = await create_resource(
        client, alice, "/deals/", {"title": "Engine", "contact_id": contact["id"]}
    )

    await _post(client, alice, f"/contacts/{contact['id']}/archive")

    assert (await _get(client, alice, f"/interactions/{interaction['id']}"))["contact_ids"] == [
        contact["id"]
    ]
    kept_task = await _get(client, alice, f"/tasks/{task['id']}")
    assert kept_task["contact_id"] == contact["id"]
    assert kept_task["contact_name"] == "Ada Lovelace"
    assert (await _get(client, alice, f"/deals/{deal['id']}"))["contact_id"] == contact["id"]
    # And each of them is still listed under that contact.
    listed = await _get(client, alice, f"/interactions/?contact_id={contact['id']}")
    assert [i["id"] for i in listed["items"]] == [interaction["id"]]


async def test_an_entry_can_still_be_edited_while_one_of_its_contacts_is_archived(
    client: AsyncClient, alice: Account
) -> None:
    """The edit form sends every link back; refusing the archived one would
    make the entry uneditable until the contact was restored."""
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada Lovelace"})
    interaction = await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Intro call", "occurred_at": YESTERDAY, "contact_ids": [contact["id"]]},
    )
    await _post(client, alice, f"/contacts/{contact['id']}/archive")

    response = await client.patch(
        f"/interactions/{interaction['id']}",
        json={"subject": "Intro call, rescheduled", "contact_ids": [contact["id"]]},
        headers=alice.headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["contact_ids"] == [contact["id"]]


async def test_an_archived_contact_is_not_counted_at_its_company(
    client: AsyncClient, alice: Account
) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    payload = {"organization_id": organization["id"]}
    await create_resource(client, alice, "/contacts/", {"name": "Ada", **payload})
    gone = await create_resource(client, alice, "/contacts/", {"name": "Grace", **payload})

    await _post(client, alice, f"/contacts/{gone['id']}/archive")

    # The number links to the list of people, so the two have to agree.
    assert (await _get(client, alice, f"/organizations/{organization['id']}"))["contact_count"] == 1
    listed = await _get(client, alice, "/organizations/")
    assert listed["items"][0]["contact_count"] == 1
    people = await _get(client, alice, f"/contacts/?organization_id={organization['id']}")
    assert [c["name"] for c in people["items"]] == ["Ada"]


async def test_archiving_a_company_leaves_its_people_in_place(
    client: AsyncClient, alice: Account
) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    contact = await create_resource(
        client, alice, "/contacts/", {"name": "Ada", "organization_id": organization["id"]}
    )

    await _post(client, alice, f"/organizations/{organization['id']}/archive")

    # Nothing cascades: the person is still on the list, still filed under it.
    kept = await _get(client, alice, f"/contacts/{contact['id']}")
    assert kept["archived_at"] is None
    assert kept["organization_id"] == organization["id"]
    assert kept["organization_name"] == "ACME"


# --- Deals: off the board, out of the numbers --------------------------------


async def test_an_archived_deal_cannot_be_moved(client: AsyncClient, alice: Account) -> None:
    deal = await create_resource(client, alice, "/deals/", {"title": "Engine"})
    await _post(client, alice, f"/deals/{deal['id']}/archive")

    response = await client.post(
        f"/deals/{deal['id']}/stage", json={"stage": "won"}, headers=alice.headers
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Deal is archived"
    assert (await _get(client, alice, f"/deals/{deal['id']}"))["stage"] == "lead"


async def test_an_archived_deal_leaves_the_dashboard(client: AsyncClient, alice: Account) -> None:
    deal = await create_resource(
        client, alice, "/deals/", {"title": "Engine", "fixed_value": "5000.00"}
    )

    async def numbers() -> tuple[int, int, int]:
        dashboard = await _get(client, alice, "/metrics/dashboard")
        return (
            sum(stage["count"] for stage in dashboard["pipeline"]["by_stage"]),
            dashboard["attention"]["stalled_deals"]["count"],
            dashboard["activity"]["deals_opened"],
        )

    assert await numbers() == (1, 1, 1)

    await _post(client, alice, f"/deals/{deal['id']}/archive")

    assert await numbers() == (0, 0, 0)
    # The list behind the count agrees with it.
    assert (await _get(client, alice, "/deals/?stalled=true"))["total"] == 0

    await _post(client, alice, f"/deals/{deal['id']}/restore")

    assert await numbers() == (1, 1, 1)


async def test_an_archived_task_is_no_next_step(client: AsyncClient, alice: Account) -> None:
    """A task no list shows will never come due in front of anyone."""
    deal = await create_resource(client, alice, "/deals/", {"title": "Engine"})
    task = await create_resource(
        client, alice, "/tasks/", {"title": "Send the offer", "deal_id": deal["id"]}
    )
    assert (await _get(client, alice, f"/deals/{deal['id']}"))["has_next_step"] is True

    await _post(client, alice, f"/tasks/{task['id']}/archive")

    assert (await _get(client, alice, f"/deals/{deal['id']}"))["has_next_step"] is False


async def test_an_archived_meeting_is_no_next_step(client: AsyncClient, alice: Account) -> None:
    deal = await create_resource(client, alice, "/deals/", {"title": "Engine"})
    meeting = await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Kickoff", "occurred_at": TOMORROW, "deal_ids": [deal["id"]]},
    )
    assert (await _get(client, alice, f"/deals/{deal['id']}"))["has_next_step"] is True

    await _post(client, alice, f"/interactions/{meeting['id']}/archive")

    assert (await _get(client, alice, f"/deals/{deal['id']}"))["has_next_step"] is False


# --- The briefing ------------------------------------------------------------


async def test_nothing_archived_is_in_the_briefing(client: AsyncClient, alice: Account) -> None:
    task = await create_resource(
        client, alice, "/tasks/", {"title": "Overdue", "due_date": "2020-01-01T09:00:00Z"}
    )
    interaction = await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Never confirmed", "occurred_at": "2020-01-01T09:00:00Z", "done": False},
    )
    watch = await create_resource(
        client,
        alice,
        "/watches/",
        {"name": "Tenders", "url": "https://example.com", "recurrence_rule": "weekly"},
    )
    capture = await create_resource(client, alice, "/captures/", {"raw": "Ada Lovelace"})
    deal = await create_resource(client, alice, "/deals/", {"title": "Engine"})

    sections = (
        "overdue_tasks",
        "unconfirmed_interactions",
        "watches_due",
        "captures_waiting",
        "stalled_deals",
    )

    async def sizes() -> list[int]:
        briefing = await _get(client, alice, "/briefing/")
        return [len(briefing[section]) for section in sections]

    assert await sizes() == [1, 1, 1, 1, 1]

    for path in (
        f"/tasks/{task['id']}",
        f"/interactions/{interaction['id']}",
        f"/watches/{watch['id']}",
        f"/captures/{capture['id']}",
        f"/deals/{deal['id']}",
    ):
        await _post(client, alice, f"{path}/archive")

    assert await sizes() == [0, 0, 0, 0, 0]


# --- Tasks -------------------------------------------------------------------


async def test_an_archived_task_cannot_be_completed(client: AsyncClient, alice: Account) -> None:
    """Completing a repeating task schedules the next one; archiving must not."""
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Weekly review", "due_date": TOMORROW, "recurrence_rule": "weekly"},
    )
    await _post(client, alice, f"/tasks/{task['id']}/archive")

    response = await client.patch(
        f"/tasks/{task['id']}", json={"done": True}, headers=alice.headers
    )

    assert response.status_code == 409
    # No successor was spawned: the series stopped where it was put away.
    everything = await _get(client, alice, "/tasks/?include_done=true")
    archive = await _get(client, alice, "/tasks/?include_done=true&archived=true")
    assert everything["total"] == 0
    assert [t["done"] for t in archive["items"]] == [False]


# --- Watches -----------------------------------------------------------------


async def test_an_archived_watch_cannot_be_swept(client: AsyncClient, alice: Account) -> None:
    watch = await create_resource(
        client,
        alice,
        "/watches/",
        {"name": "Tenders", "url": "https://example.com", "recurrence_rule": "weekly"},
    )
    await _post(client, alice, f"/watches/{watch['id']}/archive")

    response = await client.post(
        f"/watches/{watch['id']}/check", json={"outcome": "nothing"}, headers=alice.headers
    )

    assert response.status_code == 409
    after = await _get(client, alice, f"/watches/{watch['id']}")
    assert after["check_count"] == 0
    assert after["next_due_at"] == watch["next_due_at"]
    # Archived is not paused: the switch is as it was.
    assert after["active"] is True


async def test_archiving_a_watch_keeps_its_history(client: AsyncClient, alice: Account) -> None:
    watch = await create_resource(
        client,
        alice,
        "/watches/",
        {"name": "Tenders", "url": "https://example.com", "recurrence_rule": "weekly"},
    )
    checked = await client.post(
        f"/watches/{watch['id']}/check", json={"outcome": "nothing"}, headers=alice.headers
    )
    assert checked.status_code == 201, checked.text

    await _post(client, alice, f"/watches/{watch['id']}/archive")

    history = await _get(client, alice, f"/watches/{watch['id']}/checks")
    assert history["total"] == 1


# --- Captures: Undo is still one step ----------------------------------------


async def test_a_capture_nobody_worked_is_deleted_without_archiving(
    client: AsyncClient, alice: Account
) -> None:
    """What Undo in the quick-add box calls. A typo is not a record."""
    capture = await create_resource(client, alice, "/captures/", {"raw": "Ada Lovlace"})

    response = await client.delete(f"/captures/{capture['id']}", headers=alice.headers)

    assert response.status_code == 204
    assert (
        await client.get(f"/captures/{capture['id']}", headers=alice.headers)
    ).status_code == 404


async def test_a_worked_capture_is_only_deleted_once_it_was_archived(
    client: AsyncClient, alice: Account
) -> None:
    capture = await create_resource(client, alice, "/captures/", {"raw": "Ada Lovelace"})
    await _post(client, alice, f"/captures/{capture['id']}/dismiss")

    refused = await client.delete(f"/captures/{capture['id']}", headers=alice.headers)

    # Dismissing was a decision, and a decision is a record.
    assert refused.status_code == 409
    assert (await erase(client, alice, f"/captures/{capture['id']}")).status_code == 204


@pytest.mark.parametrize("action", ["dismiss", "convert"])
async def test_an_archived_capture_cannot_be_worked(
    action: str, client: AsyncClient, alice: Account
) -> None:
    capture = await create_resource(client, alice, "/captures/", {"raw": "Ada Lovelace"})
    await _post(client, alice, f"/captures/{capture['id']}/archive")

    response = await client.post(
        f"/captures/{capture['id']}/{action}",
        json={"contact": {"name": "Ada Lovelace"}} if action == "convert" else None,
        headers=alice.headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Capture is archived"
    assert (await _get(client, alice, f"/captures/{capture['id']}"))["status"] == "new"
    assert (await _get(client, alice, "/contacts/"))["total"] == 0


async def test_an_archived_capture_is_not_waiting(client: AsyncClient, alice: Account) -> None:
    capture = await create_resource(client, alice, "/captures/", {"raw": "Ada Lovelace"})
    assert (await _get(client, alice, "/captures/count"))["new"] == 1

    await _post(client, alice, f"/captures/{capture['id']}/archive")

    assert await _get(client, alice, "/captures/count") == {"new": 0, "oldest_days": None}


# --- Documents: put away, still readable -------------------------------------


async def _upload(client: AsyncClient, account: Account) -> dict[str, Any]:
    response = await client.post(
        "/documents/",
        data={"title": "Contract", "tags": "[]"},
        files={"file": ("contract.txt", b"signed\n", "text/plain")},
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    uploaded: dict[str, Any] = response.json()
    return uploaded


async def test_an_archived_document_can_still_be_read(client: AsyncClient, alice: Account) -> None:
    document = await _upload(client, alice)
    await _post(client, alice, f"/documents/{document['id']}/archive")

    content = await client.get(f"/documents/{document['id']}/content", headers=alice.headers)

    assert content.status_code == 200
    assert content.content == b"signed\n"


async def test_an_archived_documents_file_cannot_be_replaced(
    client: AsyncClient, alice: Account
) -> None:
    document = await _upload(client, alice)
    await _post(client, alice, f"/documents/{document['id']}/archive")

    response = await client.put(
        f"/documents/{document['id']}/content",
        files={"file": ("contract.txt", b"forged\n", "text/plain")},
        headers=alice.headers,
    )

    assert response.status_code == 409
    content = await client.get(f"/documents/{document['id']}/content", headers=alice.headers)
    assert content.content == b"signed\n"
