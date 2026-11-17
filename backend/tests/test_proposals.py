"""Agent proposals (#321): staged by a token, decided by the signed-in operator.

The point of the feature is what does *not* happen: nothing reaches the CRM
until approval, and a change that fails on approval leaves everything as it
was. So most tests check the other tables as well as the proposal.
"""

import uuid
from typing import Any

import pytest
from httpx2 import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditEvent
from app.models import Contact, Deal, DealStageEvent, Organization, Task
from app.models.proposal import AgentProposal
from tests.conftest import Account, create_resource

TOKENS = "/users/me/api-tokens/"
SUBMIT = "/v1/agent/proposals"
INBOX = "/proposals/"


async def propose_token(client: AsyncClient, account: Account) -> dict[str, str]:
    response = await client.post(
        TOKENS, json={"name": "claude-code", "scopes": ["read", "propose"]}, headers=account.headers
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def agent(client: AsyncClient, alice: Account) -> dict[str, str]:
    return await propose_token(client, alice)


async def submit(
    client: AsyncClient,
    agent: dict[str, str],
    entity_type: str,
    action: str,
    payload: dict[str, Any] | None = None,
    target_id: str | None = None,
    reason: str = "Extracted from conference notes",
) -> Any:
    body: dict[str, Any] = {
        "entity_type": entity_type,
        "action": action,
        "payload": payload or {},
        "reason": reason,
    }
    if target_id is not None:
        body["target_id"] = target_id
    return await client.post(SUBMIT, json=body, headers=agent)


async def staged(client: AsyncClient, agent: dict[str, str], *args: Any, **kwargs: Any) -> str:
    response = await submit(client, agent, *args, **kwargs)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "pending"
    return str(response.json()["id"])


async def count(session_factory: async_sessionmaker[AsyncSession], model: Any) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def organization(client: AsyncClient, account: Account, name: str = "ACME GmbH") -> str:
    return str((await create_resource(client, account, "/organizations/", {"name": name}))["id"])


# --- Submitting --------------------------------------------------------------


@pytest.mark.parametrize(
    ("entity_type", "payload"),
    [
        ("contact", {"name": "Maria Huber"}),
        ("organization", {"name": "Initech"}),
        ("deal", {"title": "Website relaunch"}),
        ("task", {"title": "Call Maria"}),
        (
            "interaction",
            {"subject": "Kickoff", "occurred_at": "2026-11-10T10:00:00Z", "kind": "meeting"},
        ),
    ],
)
async def test_every_entity_type_can_be_proposed_as_a_create(
    client: AsyncClient,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    entity_type: str,
    payload: dict[str, Any],
) -> None:
    response = await submit(client, agent, entity_type, "create", payload)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "status"}
    assert await count(session_factory, AgentProposal) == 1
    # Staged, not written.
    assert await count(session_factory, Contact) == 0
    assert await count(session_factory, Organization) == 0
    assert await count(session_factory, Deal) == 0
    assert await count(session_factory, Task) == 0


async def test_an_update_and_an_archive_are_accepted_for_an_owned_target(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    update = await submit(
        client, agent, "contact", "update", {"job_title": "CTO"}, target_id=contact["id"]
    )
    archive = await submit(client, agent, "contact", "archive", target_id=contact["id"])
    assert update.status_code == 201
    assert archive.status_code == 201


async def test_the_stored_payload_holds_only_what_was_sent_and_the_token(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "Maria Huber"})
    async with session_factory() as session:
        row = await session.get(AgentProposal, uuid.UUID(proposal_id))
        assert row is not None
        assert row.proposed_payload == {"name": "Maria Huber"}
        assert row.api_token_id is not None
        assert row.user_id == alice.id
        assert row.status == "pending"
        assert row.reason == "Extracted from conference notes"


async def test_a_read_only_token_is_forbidden(client: AsyncClient, alice: Account) -> None:
    created = await client.post(TOKENS, json={"name": "ro"}, headers=alice.headers)
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    response = await submit(client, bearer, "contact", "create", {"name": "X"})
    assert response.status_code == 403


async def test_a_session_or_no_credential_is_refused(client: AsyncClient, alice: Account) -> None:
    body = {"entity_type": "contact", "action": "create", "payload": {"name": "X"}, "reason": "r"}
    assert (await client.post(SUBMIT, json=body, headers=alice.headers)).status_code == 401
    assert (await client.post(SUBMIT, json=body)).status_code == 401


@pytest.mark.parametrize(
    ("entity_type", "payload"),
    [
        ("contact", {}),  # name missing
        ("contact", {"name": "X", "lifecycle_status": "nonsense"}),
        ("deal", {"title": "X", "stage": "unknown-stage"}),
        ("task", {"title": "X", "priority": "urgent!!"}),
    ],
)
async def test_a_payload_the_create_schema_refuses_is_422(
    client: AsyncClient, agent: dict[str, str], entity_type: str, payload: dict[str, Any]
) -> None:
    response = await submit(client, agent, entity_type, "create", payload)
    assert response.status_code == 422


async def test_target_id_must_match_the_action(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    with_target = await submit(
        client, agent, "contact", "create", {"name": "X"}, target_id=contact["id"]
    )
    assert with_target.status_code == 422
    for action, payload in (("update", {"job_title": "CTO"}), ("archive", None)):
        without = await submit(client, agent, "contact", action, payload)
        assert without.status_code == 422


async def test_an_empty_update_or_a_non_empty_archive_is_422(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    empty = await submit(client, agent, "contact", "update", {}, target_id=contact["id"])
    full = await submit(client, agent, "contact", "archive", {"name": "Y"}, target_id=contact["id"])
    assert empty.status_code == 422
    assert full.status_code == 422


async def test_version_cannot_be_proposed(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    response = await submit(
        client, agent, "contact", "update", {"job_title": "CTO", "version": 1}, contact["id"]
    )
    assert response.status_code == 422


async def test_an_empty_reason_is_422(client: AsyncClient, agent: dict[str, str]) -> None:
    response = await submit(client, agent, "contact", "create", {"name": "X"}, reason="   ")
    assert response.status_code == 422


async def test_another_tenants_target_or_reference_is_404(
    client: AsyncClient, alice: Account, bob: Account, agent: dict[str, str]
) -> None:
    bobs_org = await organization(client, bob)
    bobs_contact = await create_resource(client, bob, "/contacts/", {"name": "Bob's"})
    reference = await submit(
        client, agent, "contact", "create", {"name": "X", "organization_id": bobs_org}
    )
    target = await submit(
        client, agent, "contact", "update", {"job_title": "CTO"}, target_id=bobs_contact["id"]
    )
    missing = await submit(client, agent, "contact", "archive", target_id=str(uuid.uuid4()))
    assert (reference.status_code, target.status_code, missing.status_code) == (404, 404, 404)


async def test_a_link_list_reference_is_checked_too(
    client: AsyncClient, bob: Account, agent: dict[str, str]
) -> None:
    bobs_contact = await create_resource(client, bob, "/contacts/", {"name": "Bob's"})
    response = await submit(
        client,
        agent,
        "interaction",
        "create",
        {
            "subject": "Call",
            "occurred_at": "2026-11-10T10:00:00Z",
            "contact_ids": [bobs_contact["id"]],
        },
    )
    assert response.status_code == 404


async def test_an_archived_target_is_409(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    await client.post(f"/contacts/{contact['id']}/archive", headers=alice.headers)
    response = await submit(
        client, agent, "contact", "update", {"job_title": "CTO"}, target_id=contact["id"]
    )
    assert response.status_code == 409


# --- Listing -----------------------------------------------------------------


async def test_the_inbox_lists_pending_oldest_first_with_provenance(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    first = await staged(client, agent, "contact", "create", {"name": "First"})
    second = await staged(client, agent, "task", "create", {"title": "Second"})

    page = (await client.get(INBOX, headers=alice.headers)).json()
    assert [item["id"] for item in page["items"]] == [first, second]
    assert page["total"] == 2
    assert page["items"][0]["token_name"] == "claude-code"
    assert page["items"][0]["reason"] == "Extracted from conference notes"
    assert page["items"][0]["current"] is None


async def test_the_inbox_filters_by_status_and_entity_type(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact_id = await staged(client, agent, "contact", "create", {"name": "A"})
    task_id = await staged(client, agent, "task", "create", {"title": "B"})
    await client.post(f"{INBOX}{contact_id}/reject", headers=alice.headers)

    pending = (await client.get(INBOX, headers=alice.headers)).json()
    rejected = (await client.get(f"{INBOX}?status=rejected", headers=alice.headers)).json()
    tasks = (await client.get(f"{INBOX}?entity_type=task", headers=alice.headers)).json()
    contacts = (await client.get(f"{INBOX}?entity_type=contact", headers=alice.headers)).json()
    assert [i["id"] for i in pending["items"]] == [task_id]
    assert [i["id"] for i in rejected["items"]] == [contact_id]
    assert [i["id"] for i in tasks["items"]] == [task_id]
    assert contacts["items"] == []


async def test_an_update_carries_the_current_values_and_version(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(
        client, alice, "/contacts/", {"name": "Maria", "job_title": "Engineer"}
    )
    await staged(
        client, agent, "contact", "update", {"job_title": "CTO", "city": "Wien"}, contact["id"]
    )
    [item] = (await client.get(INBOX, headers=alice.headers)).json()["items"]
    assert item["current"] == {"job_title": "Engineer", "city": None, "version": contact["version"]}
    assert item["target_label"] == "Maria"


async def test_labels_resolve_referenced_names(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    org_id = await organization(client, alice)
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    await staged(
        client,
        agent,
        "interaction",
        "create",
        {
            "subject": "Call",
            "occurred_at": "2026-11-10T10:00:00Z",
            "contact_ids": [contact["id"]],
            "organization_ids": [org_id],
        },
    )
    page = (await client.get(INBOX, headers=alice.headers)).json()
    assert page["labels"] == {contact["id"]: "Maria", org_id: "ACME GmbH"}


async def test_the_count_is_the_pending_total(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    assert (await client.get(f"{INBOX}count", headers=alice.headers)).json() == {"pending": 0}
    first = await staged(client, agent, "contact", "create", {"name": "A"})
    await staged(client, agent, "contact", "create", {"name": "B"})
    assert (await client.get(f"{INBOX}count", headers=alice.headers)).json() == {"pending": 2}
    await client.post(f"{INBOX}{first}/reject", headers=alice.headers)
    assert (await client.get(f"{INBOX}count", headers=alice.headers)).json() == {"pending": 1}


async def test_another_tenant_sees_and_decides_nothing(
    client: AsyncClient, alice: Account, bob: Account, agent: dict[str, str]
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "A"})
    assert (await client.get(INBOX, headers=bob.headers)).json()["items"] == []
    assert (await client.get(f"{INBOX}count", headers=bob.headers)).json() == {"pending": 0}
    approve = await client.post(f"{INBOX}{proposal_id}/approve", headers=bob.headers)
    reject = await client.post(f"{INBOX}{proposal_id}/reject", headers=bob.headers)
    assert (approve.status_code, reject.status_code) == (404, 404)


async def test_a_token_cannot_use_the_review_routes(
    client: AsyncClient, agent: dict[str, str]
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "A"})
    assert (await client.get(INBOX, headers=agent)).status_code == 401
    assert (await client.get(f"{INBOX}count", headers=agent)).status_code == 401
    assert (await client.post(f"{INBOX}{proposal_id}/approve", headers=agent)).status_code == 401
    assert (await client.post(f"{INBOX}{proposal_id}/reject", headers=agent)).status_code == 401


# --- Approving ---------------------------------------------------------------


async def test_approving_a_contact_create_makes_the_contact(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await organization(client, alice)
    proposal_id = await staged(
        client, agent, "contact", "create", {"name": "Maria", "organization_id": org_id}
    )
    response = await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_at"] is not None
    contact = (await client.get(f"/contacts/{body['target_id']}", headers=alice.headers)).json()
    assert contact["name"] == "Maria"
    assert contact["organization_id"] == org_id
    assert await count(session_factory, Contact) == 1


async def test_approving_a_deal_update_runs_the_stage_rules(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deal = await create_resource(client, alice, "/deals/", {"title": "Website", "stage": "lead"})
    proposal_id = await staged(client, agent, "deal", "update", {"stage": "won"}, deal["id"])
    response = await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    assert response.status_code == 200, response.text
    after = (await client.get(f"/deals/{deal['id']}", headers=alice.headers)).json()
    assert after["stage"] == "won"
    assert after["closed_at"] is not None
    async with session_factory() as session:
        events = await session.scalars(
            select(DealStageEvent).where(DealStageEvent.deal_id == uuid.UUID(deal["id"]))
        )
        assert [e.to_stage for e in events] == ["lead", "won"]


async def test_approving_a_task_create(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    proposal_id = await staged(
        client, agent, "task", "create", {"title": "Call Maria", "due_date": "2026-12-01"}
    )
    body = (await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)).json()
    task = (await client.get(f"/tasks/{body['target_id']}", headers=alice.headers)).json()
    assert task["title"] == "Call Maria"
    assert task["due_date"].startswith("2026-12-01")


async def test_approving_an_interaction_links_its_contacts(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    proposal_id = await staged(
        client,
        agent,
        "interaction",
        "create",
        {
            "subject": "Kickoff",
            "occurred_at": "2026-11-10T10:00:00Z",
            "contact_ids": [contact["id"]],
        },
    )
    body = (await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)).json()
    interaction = (
        await client.get(f"/interactions/{body['target_id']}", headers=alice.headers)
    ).json()
    assert interaction["contact_ids"] == [contact["id"]]


async def test_approving_an_archive_archives_the_record(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    org_id = await organization(client, alice)
    proposal_id = await staged(client, agent, "organization", "archive", target_id=org_id)
    response = await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    assert response.status_code == 200
    assert response.json()["target_id"] == org_id
    after = (await client.get(f"/organizations/{org_id}", headers=alice.headers)).json()
    assert after["archived_at"] is not None


async def test_approving_a_completion_spawns_the_next_recurring_task(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    task = await create_resource(
        client,
        alice,
        "/tasks/",
        {
            "title": "Monthly check",
            "due_date": "2026-12-01T09:00:00Z",
            "recurrence_rule": "monthly",
        },
    )
    proposal_id = await staged(
        client, agent, "task", "update", {"done": True}, target_id=str(task["id"])
    )
    response = await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    assert response.status_code == 200, response.text
    tasks = (await client.get("/tasks/", headers=alice.headers)).json()
    items = tasks["items"] if isinstance(tasks, dict) else tasks
    successors = [t for t in items if t.get("recurrence_parent_id") == task["id"]]
    assert len(successors) == 1
    assert successors[0]["done"] is False
    assert successors[0]["title"] == "Monthly check"


async def test_approving_an_update_writes_the_change_history(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    proposal_id = await staged(
        client, agent, "contact", "update", {"job_title": "CTO"}, contact["id"]
    )
    await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    async with session_factory() as session:
        events = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(contact["id"]))
            )
        ).all()
    assert [e.action for e in events] == ["update"]


async def test_an_edited_payload_is_applied_and_the_original_kept(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "Maria Hubr"})
    response = await client.post(
        f"{INBOX}{proposal_id}/approve",
        json={"payload": {"name": "Maria Huber", "city": "Graz"}},
        headers=alice.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposed_payload"] == {"name": "Maria Hubr"}
    assert body["applied_payload"] == {"name": "Maria Huber", "city": "Graz"}
    contact = (await client.get(f"/contacts/{body['target_id']}", headers=alice.headers)).json()
    assert (contact["name"], contact["city"]) == ("Maria Huber", "Graz")


async def test_an_invalid_edit_is_422_and_the_proposal_stays_pending(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "Maria"})
    response = await client.post(
        f"{INBOX}{proposal_id}/approve", json={"payload": {"city": "Graz"}}, headers=alice.headers
    )
    assert response.status_code == 422
    assert (await client.get(f"{INBOX}count", headers=alice.headers)).json() == {"pending": 1}


async def test_a_stale_version_is_409_and_the_proposal_stays_pending(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    proposal_id = await staged(
        client, agent, "contact", "update", {"job_title": "CTO"}, contact["id"]
    )
    await client.patch(f"/contacts/{contact['id']}", json={"city": "Linz"}, headers=alice.headers)
    response = await client.post(
        f"{INBOX}{proposal_id}/approve", json={"version": contact["version"]}, headers=alice.headers
    )
    assert response.status_code == 409
    assert (await client.get(f"{INBOX}count", headers=alice.headers)).json() == {"pending": 1}
    unchanged = (await client.get(f"/contacts/{contact['id']}", headers=alice.headers)).json()
    assert unchanged["job_title"] is None


async def test_a_reference_that_went_away_changes_nothing(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await organization(client, alice)
    proposal_id = await staged(
        client, agent, "contact", "create", {"name": "Maria", "organization_id": org_id}
    )
    await client.post(f"/organizations/{org_id}/archive", headers=alice.headers)
    erased = await client.delete(f"/organizations/{org_id}", headers=alice.headers)
    assert erased.status_code == 204

    response = await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    assert response.status_code == 404
    assert await count(session_factory, Contact) == 0
    async with session_factory() as session:
        row = await session.get(AgentProposal, uuid.UUID(proposal_id))
        assert row is not None
        assert (row.status, row.reviewed_at, row.target_id) == ("pending", None, None)


async def test_a_second_approve_is_409(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "Maria"})
    assert (
        await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    ).status_code == 200
    again = await client.post(f"{INBOX}{proposal_id}/approve", headers=alice.headers)
    assert again.status_code == 409
    assert await count(session_factory, Contact) == 1


# --- Rejecting ---------------------------------------------------------------


async def test_rejecting_records_the_note_and_changes_no_data(
    client: AsyncClient,
    alice: Account,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "Maria"})
    response = await client.post(
        f"{INBOX}{proposal_id}/reject",
        json={"rejection_reason": "  Not a real person  "},
        headers=alice.headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["rejection_reason"]) == ("rejected", "Not a real person")
    assert body["reviewed_at"] is not None
    assert await count(session_factory, Contact) == 0


async def test_rejecting_needs_no_body_and_a_long_note_is_refused(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    proposal_id = await staged(client, agent, "contact", "create", {"name": "Maria"})
    too_long = await client.post(
        f"{INBOX}{proposal_id}/reject",
        json={"rejection_reason": "x" * 2001},
        headers=alice.headers,
    )
    assert too_long.status_code == 422
    plain = await client.post(f"{INBOX}{proposal_id}/reject", headers=alice.headers)
    assert plain.status_code == 200
    assert plain.json()["rejection_reason"] is None


async def test_a_decided_proposal_cannot_be_decided_again(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    approved = await staged(client, agent, "contact", "create", {"name": "A"})
    rejected = await staged(client, agent, "contact", "create", {"name": "B"})
    await client.post(f"{INBOX}{approved}/approve", headers=alice.headers)
    await client.post(f"{INBOX}{rejected}/reject", headers=alice.headers)
    for proposal_id in (approved, rejected):
        for action in ("approve", "reject"):
            response = await client.post(f"{INBOX}{proposal_id}/{action}", headers=alice.headers)
            assert response.status_code == 409


# --- Review findings ---------------------------------------------------------


async def test_organization_proposals_list_with_current_values(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    org_id = await organization(client, alice)
    await staged(client, agent, "organization", "update", {"name": "ACME AG"}, org_id)
    await staged(client, agent, "organization", "archive", target_id=org_id)
    response = await client.get(INBOX, headers=alice.headers)
    assert response.status_code == 200
    update, archive = response.json()["items"]
    assert update["current"]["name"] == "ACME GmbH"
    assert update["target_label"] == "ACME GmbH"
    assert set(archive["current"]) == {"archived_at", "version"}


async def test_archive_approval_with_a_stale_version_is_409(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    proposal_id = await staged(client, agent, "contact", "archive", target_id=contact["id"])
    await client.patch(f"/contacts/{contact['id']}", json={"city": "Linz"}, headers=alice.headers)
    stale = await client.post(
        f"{INBOX}{proposal_id}/approve", json={"version": contact["version"]}, headers=alice.headers
    )
    assert stale.status_code == 409
    after = (await client.get(f"/contacts/{contact['id']}", headers=alice.headers)).json()
    assert after["archived_at"] is None


@pytest.mark.parametrize(
    ("entity_type", "payload"),
    [
        ("contact", {"name": "Maria", "known_day_rate": 100}),
        ("deal", {"title": "Relaunch", "lost_reason": "too dear"}),
        ("deal", {"title": "Relaunch", "value_type": "fixed", "rate": 100, "rate_unit": "day"}),
    ],
)
async def test_a_create_the_router_would_refuse_is_422_at_submission(
    client: AsyncClient,
    agent: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    entity_type: str,
    payload: dict[str, Any],
) -> None:
    response = await submit(client, agent, entity_type, "create", payload)
    assert response.status_code == 422, response.text
    assert await count(session_factory, AgentProposal) == 0
    assert await count(session_factory, Contact) == 0
    assert await count(session_factory, Deal) == 0


async def test_an_update_the_router_would_refuse_is_422_and_changes_nothing(
    client: AsyncClient, alice: Account, agent: dict[str, str]
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Maria"})
    response = await submit(
        client, agent, "contact", "update", {"known_day_rate": 100}, contact["id"]
    )
    assert response.status_code == 422
    after = (await client.get(f"/contacts/{contact['id']}", headers=alice.headers)).json()
    assert after["version"] == contact["version"]
    assert after["known_day_rate"] is None
