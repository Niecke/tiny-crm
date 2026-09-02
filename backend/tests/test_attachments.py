"""Filing documents and interactions against the records they are about.

Documents could only belong to a project and interactions only to contacts, so
a signed contract had nowhere to sit against its deal and "every call about this
deal" had no answer. Six join tables fix it — real tables with real foreign
keys, because a polymorphic (target_type, target_id) column cannot have one and
would leave rows pointing at deleted records.

The details that are not plain CRUD: every id in every link list is checked
against the caller's own rows, an upload whose links are bad must not leave an
orphan in the object store, and deleting a linked record must drop the *link*
without touching the document at the other end of it.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

import pytest
from httpx2 import AsyncClient

from app.routers import documents
from tests.conftest import Account, create_resource

OCCURRED_AT = (datetime.now(UTC) - timedelta(days=1)).isoformat()


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, bytes]]:
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


async def _upload(
    client: AsyncClient, account: Account, title: str = "Signed contract", **links: str
) -> dict[str, Any]:
    response = await client.post(
        "/documents/",
        data={"title": title, "tags": "[]", **links},
        files={"file": ("contract.txt", b"signed\n", "text/plain")},
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    uploaded: dict[str, Any] = response.json()
    return uploaded


async def _records(client: AsyncClient, account: Account) -> dict[str, dict[str, Any]]:
    """One of each thing a document or interaction can be filed against."""
    return {
        "contact": await create_resource(client, account, "/contacts/", {"name": "Ada"}),
        "organization": await create_resource(client, account, "/organizations/", {"name": "ACME"}),
        "deal": await create_resource(client, account, "/deals/", {"title": "Website relaunch"}),
        "project": await create_resource(
            client, account, "/projects/", {"name": "Relaunch", "start_date": "2026-08-01"}
        ),
    }


async def _interaction(
    client: AsyncClient, account: Account, subject: str = "Kickoff call", **links: list[str]
) -> dict[str, Any]:
    payload: dict[str, Any] = {"subject": subject, "occurred_at": OCCURRED_AT}
    payload.update(links)
    return await create_resource(client, account, "/interactions/", payload)


# --- Documents --------------------------------------------------------------


async def test_a_document_is_filed_against_every_kind_of_record(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    records = await _records(client, alice)

    uploaded = await _upload(
        client,
        alice,
        contact_ids=f'["{records["contact"]["id"]}"]',
        organization_ids=f'["{records["organization"]["id"]}"]',
        deal_ids=f'["{records["deal"]["id"]}"]',
        project_ids=f'["{records["project"]["id"]}"]',
    )

    # Attached as it arrives, not in a second step.
    assert uploaded["contact_ids"] == [records["contact"]["id"]]
    assert uploaded["organization_ids"] == [records["organization"]["id"]]
    assert uploaded["deal_ids"] == [records["deal"]["id"]]
    assert uploaded["project_ids"] == [records["project"]["id"]]

    fetched = await client.get(f"/documents/{uploaded['id']}", headers=alice.headers)
    assert fetched.json()["deal_ids"] == [records["deal"]["id"]]


async def test_a_document_with_no_links_is_still_a_document(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    uploaded = await _upload(client, alice)

    for field in ("contact_ids", "organization_ids", "deal_ids", "project_ids"):
        assert uploaded[field] == []


async def test_the_same_document_sits_under_several_records_at_once(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    # An NDA is filed against both the person and the company it was signed
    # with, without being uploaded twice.
    person = await create_resource(client, alice, "/contacts/", {"name": "Ada"})
    other = await create_resource(client, alice, "/contacts/", {"name": "Grace"})

    uploaded = await _upload(
        client, alice, title="NDA", contact_ids=f'["{person["id"]}", "{other["id"]}"]'
    )

    assert sorted(uploaded["contact_ids"]) == sorted([person["id"], other["id"]])


async def test_links_can_be_changed_and_cleared_later(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    records = await _records(client, alice)
    uploaded = await _upload(client, alice)

    attached = await client.patch(
        f"/documents/{uploaded['id']}",
        json={"deal_ids": [records["deal"]["id"]]},
        headers=alice.headers,
    )
    assert attached.status_code == 200
    assert attached.json()["deal_ids"] == [records["deal"]["id"]]

    # An empty list detaches everything; the list replaces what was there.
    detached = await client.patch(
        f"/documents/{uploaded['id']}", json={"deal_ids": []}, headers=alice.headers
    )
    assert detached.status_code == 200
    assert detached.json()["deal_ids"] == []


async def test_an_untouched_link_list_survives_an_unrelated_patch(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    records = await _records(client, alice)
    uploaded = await _upload(client, alice, deal_ids=f'["{records["deal"]["id"]}"]')

    renamed = await client.patch(
        f"/documents/{uploaded['id']}", json={"title": "Countersigned"}, headers=alice.headers
    )

    assert renamed.json()["title"] == "Countersigned"
    assert renamed.json()["deal_ids"] == [records["deal"]["id"]]


@pytest.mark.parametrize("field", ["contact_ids", "organization_ids", "deal_ids", "project_ids"])
async def test_an_unknown_link_id_is_refused_on_upload_and_patch(
    field: str, client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"

    response = await client.post(
        "/documents/",
        data={"title": "X", "tags": "[]", field: f'["{missing}"]'},
        files={"file": ("x.txt", b"x\n", "text/plain")},
        headers=alice.headers,
    )
    assert response.status_code == 404

    uploaded = await _upload(client, alice)
    patched = await client.patch(
        f"/documents/{uploaded['id']}", json={field: [missing]}, headers=alice.headers
    )
    assert patched.status_code == 404


async def test_a_refused_upload_leaves_nothing_in_the_object_store(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    # The links are resolved before the body reaches S3. Doing it the other way
    # round would leave an object in the bucket with no row that could ever
    # delete it.
    missing = "00000000-0000-0000-0000-000000000001"

    response = await client.post(
        "/documents/",
        data={"title": "X", "tags": "[]", "deal_ids": f'["{missing}"]'},
        files={"file": ("x.txt", b"x\n", "text/plain")},
        headers=alice.headers,
    )

    assert response.status_code == 404
    assert object_store == {}


async def test_a_malformed_link_list_is_a_422_not_a_500(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    for bad in ["not json", '["not-a-uuid"]', '{"deal": 1}']:
        response = await client.post(
            "/documents/",
            data={"title": "X", "tags": "[]", "deal_ids": bad},
            files={"file": ("x.txt", b"x\n", "text/plain")},
            headers=alice.headers,
        )
        assert response.status_code == 422, f"{bad} should be refused"
    assert object_store == {}


async def test_a_document_cannot_be_filed_against_another_users_record(
    client: AsyncClient, alice: Account, bob: Account, object_store: dict[str, bytes]
) -> None:
    alices = await _records(client, alice)

    for field, key in (
        ("contact_ids", "contact"),
        ("organization_ids", "organization"),
        ("deal_ids", "deal"),
        ("project_ids", "project"),
    ):
        response = await client.post(
            "/documents/",
            data={"title": "Bob's", "tags": "[]", field: f'["{alices[key]["id"]}"]'},
            files={"file": ("x.txt", b"x\n", "text/plain")},
            headers=bob.headers,
        )
        assert response.status_code == 404, f"{field} should be refused"


async def test_documents_can_be_listed_by_what_they_are_filed_against(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    records = await _records(client, alice)
    await _upload(client, alice, title="Contract", deal_ids=f'["{records["deal"]["id"]}"]')
    await _upload(client, alice, title="NDA", contact_ids=f'["{records["contact"]["id"]}"]')
    await _upload(client, alice, title="Unfiled")

    by_deal = await client.get(
        f"/documents/?deal_id={records['deal']['id']}", headers=alice.headers
    )
    assert by_deal.json()["total"] == 1
    assert by_deal.json()["items"][0]["title"] == "Contract"

    by_contact = await client.get(
        f"/documents/?contact_id={records['contact']['id']}", headers=alice.headers
    )
    assert by_contact.json()["total"] == 1
    assert by_contact.json()["items"][0]["title"] == "NDA"

    assert (await client.get("/documents/", headers=alice.headers)).json()["total"] == 3


async def test_deleting_the_record_drops_the_link_not_the_document(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    records = await _records(client, alice)
    uploaded = await _upload(
        client,
        alice,
        contact_ids=f'["{records["contact"]["id"]}"]',
        deal_ids=f'["{records["deal"]["id"]}"]',
    )

    assert (
        await client.delete(f"/deals/{records['deal']['id']}", headers=alice.headers)
    ).status_code == 204

    # CASCADE removes the join row; the file itself is not collateral damage.
    survivor = await client.get(f"/documents/{uploaded['id']}", headers=alice.headers)
    assert survivor.status_code == 200
    assert survivor.json()["deal_ids"] == []
    assert survivor.json()["contact_ids"] == [records["contact"]["id"]]


async def test_the_project_link_works_from_both_sides(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    # project_documents predates this change and was edited from the project.
    # Both directions now write the same table, so they have to agree.
    project = await create_resource(
        client, alice, "/projects/", {"name": "Relaunch", "start_date": "2026-08-01"}
    )
    uploaded = await _upload(client, alice, project_ids=f'["{project["id"]}"]')

    from_project = await client.get(f"/projects/{project['id']}", headers=alice.headers)
    assert from_project.json()["document_ids"] == [uploaded["id"]]

    second = await _upload(client, alice, title="Second")
    await client.patch(
        f"/projects/{project['id']}",
        json={"document_ids": [second["id"]]},
        headers=alice.headers,
    )

    # The project replaced its list, so the first document is detached.
    assert (await client.get(f"/documents/{uploaded['id']}", headers=alice.headers)).json()[
        "project_ids"
    ] == []
    assert (await client.get(f"/documents/{second['id']}", headers=alice.headers)).json()[
        "project_ids"
    ] == [project["id"]]


# --- Interactions -----------------------------------------------------------


async def test_an_interaction_records_everything_it_was_about(
    client: AsyncClient, alice: Account
) -> None:
    records = await _records(client, alice)

    interaction = await _interaction(
        client,
        alice,
        contact_ids=[records["contact"]["id"]],
        organization_ids=[records["organization"]["id"]],
        deal_ids=[records["deal"]["id"]],
        project_ids=[records["project"]["id"]],
    )

    # A kickoff call is with people, about a deal, under a project — all at once.
    assert interaction["contact_ids"] == [records["contact"]["id"]]
    assert interaction["organization_ids"] == [records["organization"]["id"]]
    assert interaction["deal_ids"] == [records["deal"]["id"]]
    assert interaction["project_ids"] == [records["project"]["id"]]


async def test_an_interaction_with_no_links_still_works(
    client: AsyncClient, alice: Account
) -> None:
    interaction = await _interaction(client, alice, subject="A thought")

    for field in ("contact_ids", "organization_ids", "deal_ids", "project_ids"):
        assert interaction[field] == []


async def test_interaction_links_can_be_changed_and_cleared(
    client: AsyncClient, alice: Account
) -> None:
    records = await _records(client, alice)
    interaction = await _interaction(client, alice)

    attached = await client.patch(
        f"/interactions/{interaction['id']}",
        json={"deal_ids": [records["deal"]["id"]]},
        headers=alice.headers,
    )
    assert attached.status_code == 200
    assert attached.json()["deal_ids"] == [records["deal"]["id"]]

    detached = await client.patch(
        f"/interactions/{interaction['id']}", json={"deal_ids": []}, headers=alice.headers
    )
    assert detached.json()["deal_ids"] == []


async def test_an_untouched_interaction_link_survives_a_patch(
    client: AsyncClient, alice: Account
) -> None:
    records = await _records(client, alice)
    interaction = await _interaction(client, alice, deal_ids=[records["deal"]["id"]])

    renamed = await client.patch(
        f"/interactions/{interaction['id']}", json={"subject": "Renamed"}, headers=alice.headers
    )

    assert renamed.json()["subject"] == "Renamed"
    assert renamed.json()["deal_ids"] == [records["deal"]["id"]]


@pytest.mark.parametrize("field", ["contact_ids", "organization_ids", "deal_ids", "project_ids"])
async def test_an_unknown_interaction_link_id_is_refused(
    field: str, client: AsyncClient, alice: Account
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"

    created = await client.post(
        "/interactions/",
        json={"subject": "X", "occurred_at": OCCURRED_AT, field: [missing]},
        headers=alice.headers,
    )
    assert created.status_code == 404

    interaction = await _interaction(client, alice)
    patched = await client.patch(
        f"/interactions/{interaction['id']}", json={field: [missing]}, headers=alice.headers
    )
    assert patched.status_code == 404


async def test_an_interaction_cannot_be_filed_against_another_users_record(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    alices = await _records(client, alice)

    for field, key in (
        ("contact_ids", "contact"),
        ("organization_ids", "organization"),
        ("deal_ids", "deal"),
        ("project_ids", "project"),
    ):
        response = await client.post(
            "/interactions/",
            json={"subject": "X", "occurred_at": OCCURRED_AT, field: [alices[key]["id"]]},
            headers=bob.headers,
        )
        assert response.status_code == 404, f"{field} should be refused"


async def test_interactions_can_be_listed_by_what_they_were_about(
    client: AsyncClient, alice: Account
) -> None:
    records = await _records(client, alice)
    await _interaction(client, alice, subject="Deal call", deal_ids=[records["deal"]["id"]])
    await _interaction(
        client, alice, subject="Project sync", project_ids=[records["project"]["id"]]
    )
    await _interaction(
        client, alice, subject="Company intro", organization_ids=[records["organization"]["id"]]
    )
    await _interaction(client, alice, subject="Unattached")

    # "Every call about this deal" — the question contacts alone could not answer.
    by_deal = await client.get(
        f"/interactions/?deal_id={records['deal']['id']}", headers=alice.headers
    )
    assert by_deal.json()["total"] == 1
    assert by_deal.json()["items"][0]["subject"] == "Deal call"

    by_project = await client.get(
        f"/interactions/?project_id={records['project']['id']}", headers=alice.headers
    )
    assert by_project.json()["total"] == 1

    by_org = await client.get(
        f"/interactions/?organization_id={records['organization']['id']}", headers=alice.headers
    )
    assert by_org.json()["total"] == 1

    assert (await client.get("/interactions/", headers=alice.headers)).json()["total"] == 4


async def test_the_contact_filter_still_works_alongside_the_new_ones(
    client: AsyncClient, alice: Account
) -> None:
    records = await _records(client, alice)
    await _interaction(
        client,
        alice,
        subject="Both",
        contact_ids=[records["contact"]["id"]],
        deal_ids=[records["deal"]["id"]],
    )
    await _interaction(
        client, alice, subject="Contact only", contact_ids=[records["contact"]["id"]]
    )

    by_contact = await client.get(
        f"/interactions/?contact_id={records['contact']['id']}", headers=alice.headers
    )
    assert by_contact.json()["total"] == 2

    # Two link filters at once narrow rather than widen.
    both = await client.get(
        f"/interactions/?contact_id={records['contact']['id']}&deal_id={records['deal']['id']}",
        headers=alice.headers,
    )
    assert both.json()["total"] == 1
    assert both.json()["items"][0]["subject"] == "Both"


async def test_deleting_the_record_drops_the_interaction_link_not_the_interaction(
    client: AsyncClient, alice: Account
) -> None:
    records = await _records(client, alice)
    interaction = await _interaction(
        client,
        alice,
        deal_ids=[records["deal"]["id"]],
        project_ids=[records["project"]["id"]],
    )

    assert (
        await client.delete(f"/projects/{records['project']['id']}", headers=alice.headers)
    ).status_code == 204

    survivor = await client.get(f"/interactions/{interaction['id']}", headers=alice.headers)
    assert survivor.status_code == 200
    assert survivor.json()["project_ids"] == []
    assert survivor.json()["deal_ids"] == [records["deal"]["id"]]
