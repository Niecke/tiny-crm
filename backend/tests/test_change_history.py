"""Change history and stale-save checks (#142).

Every record used to keep only `updated_at`, so "who changed this, and from
what?" had no answer, and two tabs editing the same contact silently kept
whichever saved last. Now:

*`version`* goes up on every save. A PATCH that sends the version it was edited
from is refused with 409 once someone else has saved in between.

*`audit_events`*, append-only, holds what each save actually changed — only the
fields that differ, old and new — and is read back through
GET /history/{entity_type}/{entity_id}.
"""

from typing import Any
from uuid import UUID

import pytest
from httpx2 import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditEvent
from app.models.contact import Contact
from app.routers import contacts
from tests.conftest import Account, create_resource, erase

# Imported for its autouse fixture as well: documents need the fake bucket.
from tests.test_cross_user_isolation import (  # noqa: F401
    RESOURCE_IDS,
    RESOURCES,
    Resource,
    fake_object_store,
)

Sessions = async_sessionmaker[AsyncSession]


def _entity(resource: Resource) -> str:
    """The history's name for a resource: /watches/ → "watch"."""
    return {"watches": "watch"}.get(resource.name, resource.name.removesuffix("s"))


async def _history(
    client: AsyncClient, account: Account, entity: str, row_id: str
) -> list[dict[str, Any]]:
    response = await client.get(f"/history/{entity}/{row_id}", headers=account.headers)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def _patch(
    client: AsyncClient, account: Account, path: str, body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.patch(path, json=body, headers=account.headers)
    assert response.status_code == 200, response.text
    patched: dict[str, Any] = response.json()
    return patched


# --- Stale saves -----------------------------------------------------------


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_a_save_from_an_outdated_copy_is_refused(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    path = f"{resource.path}{row['id']}"
    assert row["version"] == 1

    # The first tab saves, from the version it loaded.
    saved = await _patch(client, alice, path, {**resource.update, "version": 1})
    assert saved["version"] == 2

    # The second tab loaded version 1 too, and would overwrite that save.
    stale = await client.patch(
        path, json={**resource.update, "version": 1, **_other(resource)}, headers=alice.headers
    )
    assert stale.status_code == 409
    assert "changed elsewhere" in stale.json()["detail"]

    # Nothing of the stale save reached the row.
    current = (await client.get(path, headers=alice.headers)).json()
    assert current["version"] == 2
    for field, value in resource.update.items():
        assert current[field] == value


def _other(resource: Resource) -> dict[str, Any]:
    """A different value for the same field, so the stale save would change it."""
    return {field: f"{value} again" for field, value in resource.update.items()}


async def test_a_save_without_a_version_is_not_checked(client: AsyncClient, alice: Account) -> None:
    """What a one-field toggle sends: the newest value simply wins."""
    task = await create_resource(client, alice, "/tasks/", {"title": "Send invoice"})
    path = f"/tasks/{task['id']}"
    await _patch(client, alice, path, {"title": "Send the invoice", "version": 1})

    done = await _patch(client, alice, path, {"done": True})

    assert done["done"] is True
    assert done["version"] == 3


async def test_a_save_that_loses_the_race_is_refused_too(
    client: AsyncClient,
    alice: Account,
    session_factory: Sessions,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both requests passed the version check; only the first may write.

    The check in the router cannot see a save that commits after it has run.
    The UPDATE itself names the version it loaded, so the second one matches
    no row — and that answers 409 as well, not a 500.
    """
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada"})
    check_organization = contacts._check_organization

    async def someone_saves_meanwhile(*args: Any) -> None:
        async with session_factory() as session:
            await session.execute(
                update(Contact)
                .where(Contact.id == UUID(contact["id"]))
                .values(name="Ada King", version=Contact.version + 1)
            )
            await session.commit()
        await check_organization(*args)

    # Runs after the version check and before the write: the gap a real race
    # falls into.
    monkeypatch.setattr(contacts, "_check_organization", someone_saves_meanwhile)
    response = await client.patch(
        f"/contacts/{contact['id']}",
        json={"name": "Ada Lovelace", "organization_id": None, "version": 1},
        headers=alice.headers,
    )

    assert response.status_code == 409
    current = (await client.get(f"/contacts/{contact['id']}", headers=alice.headers)).json()
    assert current["name"] == "Ada King"


# --- What the history records ----------------------------------------------


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_every_record_keeps_its_history(
    resource: Resource, client: AsyncClient, alice: Account
) -> None:
    row = await resource.create(client, alice)
    await _patch(client, alice, f"{resource.path}{row['id']}", resource.update)

    [entry] = await _history(client, alice, _entity(resource), row["id"])

    assert entry["action"] == "update"
    assert entry["entity_id"] == row["id"]
    assert entry["actor_id"] == str(alice.id)
    assert entry["changes"] == {
        field: {"old": row[field], "new": value} for field, value in resource.update.items()
    }


async def test_only_the_fields_that_changed_are_recorded(
    client: AsyncClient, alice: Account
) -> None:
    """The edit form sends every field on every save; the history must not."""
    contact = await create_resource(
        client,
        alice,
        "/contacts/",
        {"name": "Ada", "email": "ada@example.com", "city": "London", "tags": ["math"]},
    )
    form = {k: v for k, v in contact.items() if k in {"name", "email", "city", "tags"}}

    await _patch(
        client,
        alice,
        f"/contacts/{contact['id']}",
        {**form, "email": "ada@lovelace.dev", "known_day_rate": "800", "rate_currency": "EUR"},
    )

    [entry] = await _history(client, alice, "contact", contact["id"])
    assert entry["changes"] == {
        "email": {"old": "ada@example.com", "new": "ada@lovelace.dev"},
        # An amount stays a string, like everywhere else in the API.
        "known_day_rate": {"old": None, "new": "800"},
        "rate_currency": {"old": None, "new": "EUR"},
    }


async def test_a_save_that_changes_nothing_leaves_no_trace(
    client: AsyncClient, alice: Account
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada"})

    again = await _patch(client, alice, f"/contacts/{contact['id']}", {"name": "Ada"})

    assert again["version"] == 1
    assert await _history(client, alice, "contact", contact["id"]) == []


async def test_what_the_server_changes_alongside_is_recorded_too(
    client: AsyncClient, alice: Account
) -> None:
    """Winning a deal pins its probability; the history shows both."""
    deal = await create_resource(client, alice, "/deals/", {"title": "Relaunch", "probability": 40})

    response = await client.post(
        f"/deals/{deal['id']}/stage", json={"stage": "won"}, headers=alice.headers
    )
    assert response.status_code == 200, response.text

    [entry] = await _history(client, alice, "deal", deal["id"])
    assert entry["changes"]["stage"] == {"old": "lead", "new": "won"}
    assert entry["changes"]["probability"] == {"old": 40, "new": 100}
    assert entry["changes"]["closed_at"]["old"] is None


async def test_relinking_is_a_change_like_any_other(client: AsyncClient, alice: Account) -> None:
    ada = await create_resource(client, alice, "/contacts/", {"name": "Ada"})
    call = await create_resource(
        client,
        alice,
        "/interactions/",
        {"subject": "Intro call", "occurred_at": "2026-08-01T10:00:00Z"},
    )

    linked = await _patch(
        client, alice, f"/interactions/{call['id']}", {"contact_ids": [ada["id"]], "version": 1}
    )

    # A link alone is a save too, so a stale copy cannot undo it unnoticed.
    assert linked["version"] == 2
    [entry] = await _history(client, alice, "interaction", call["id"])
    assert entry["changes"] == {"contact_ids": {"old": [], "new": [ada["id"]]}}


async def test_archiving_and_restoring_are_on_record(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada"})
    path = f"/contacts/{contact['id']}"

    await client.post(f"{path}/archive", headers=alice.headers)
    # Archiving again changes nothing, so it adds nothing.
    await client.post(f"{path}/archive", headers=alice.headers)
    await client.post(f"{path}/restore", headers=alice.headers)
    await _patch(client, alice, path, {"name": "Ada Lovelace"})

    history = await _history(client, alice, "contact", contact["id"])
    # Newest first.
    assert [entry["action"] for entry in history] == ["update", "restore", "archive"]
    assert history[1]["changes"] == {}


async def test_erasing_a_record_erases_its_history(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada"})
    await _patch(client, alice, f"/contacts/{contact['id']}", {"email": "ada@example.com"})

    response = await erase(client, alice, f"/contacts/{contact['id']}")
    assert response.status_code == 204

    async with session_factory() as session:
        left = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_id == UUID(contact["id"]))
        )
    # The old address went with the person, not into the log.
    assert left == 0


async def test_the_history_pages(client: AsyncClient, alice: Account) -> None:
    contact = await create_resource(client, alice, "/contacts/", {"name": "Ada"})
    for city in ("London", "Paris", "Vienna"):
        await _patch(client, alice, f"/contacts/{contact['id']}", {"city": city})

    response = await client.get(f"/history/contact/{contact['id']}?limit=2", headers=alice.headers)

    page = response.json()
    assert page["total"] == 3
    assert [entry["changes"]["city"]["new"] for entry in page["items"]] == ["Vienna", "Paris"]


# --- Who may read it -------------------------------------------------------


@pytest.mark.parametrize("resource", RESOURCES, ids=RESOURCE_IDS)
async def test_another_user_cannot_read_the_history(
    resource: Resource, client: AsyncClient, alice: Account, bob: Account
) -> None:
    row = await resource.create(client, alice)
    await _patch(client, alice, f"{resource.path}{row['id']}", resource.update)
    path = f"/history/{_entity(resource)}/{row['id']}"

    # 404 rather than an empty page, which would confirm the id exists.
    assert (await client.get(path, headers=bob.headers)).status_code == 404
    assert (await client.get(path)).status_code == 401


async def test_an_unknown_record_has_no_history(client: AsyncClient, alice: Account) -> None:
    missing = "00000000-0000-0000-0000-000000000001"

    response = await client.get(f"/history/contact/{missing}", headers=alice.headers)

    assert response.status_code == 404
    assert (
        await client.get(f"/history/invoice/{missing}", headers=alice.headers)
    ).status_code == 422
