"""The inbox: parking a line of text, and working through what was parked."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def test_a_capture_survives_a_full_round_trip(client: AsyncClient, alice: Account) -> None:
    created = await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})
    assert created["raw"] == "Jane Doe"
    assert created["name"] == "Jane Doe"
    assert created["url"] is None
    assert created["status"] == "new"
    assert created["triaged_at"] is None
    assert created["contact_id"] is None

    fetched = await client.get(f"/captures/{created['id']}", headers=alice.headers)
    assert fetched.status_code == 200
    assert fetched.json() == created

    patched = await client.patch(
        f"/captures/{created['id']}",
        json={"name": "Jane Doe-Smith", "note": "spoke at the Vienna meetup"},
        headers=alice.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Jane Doe-Smith"
    assert patched.json()["note"] == "spoke at the Vienna meetup"

    deleted = await client.delete(f"/captures/{created['id']}", headers=alice.headers)
    assert deleted.status_code == 204
    gone = await client.get(f"/captures/{created['id']}", headers=alice.headers)
    assert gone.status_code == 404


async def test_the_link_is_pulled_out_of_the_line(client: AsyncClient, alice: Account) -> None:
    created = await create_resource(
        client, alice, "/captures/", {"raw": "Jane Doe https://linkedin.com/in/jane-doe"}
    )
    assert created["name"] == "Jane Doe"
    assert created["url"] == "https://linkedin.com/in/jane-doe"
    # The line as typed is kept whatever the parser made of it.
    assert created["raw"] == "Jane Doe https://linkedin.com/in/jane-doe"


async def test_a_bare_profile_link_suggests_a_name(client: AsyncClient, alice: Account) -> None:
    created = await create_resource(
        client, alice, "/captures/", {"raw": "https://www.linkedin.com/in/jane-doe-4b21"}
    )
    assert created["name"] == "Jane Doe"
    assert created["url"] == "https://www.linkedin.com/in/jane-doe-4b21"


async def test_an_explicit_name_and_url_beat_the_parser(
    client: AsyncClient, alice: Account
) -> None:
    """What the share target sends: Android hands over the url separately."""
    created = await create_resource(
        client,
        alice,
        "/captures/",
        {
            "raw": "Some Article Title https://example.com/post",
            "name": "Jane Doe",
            "url": "https://example.com/other",
        },
    )
    assert created["name"] == "Jane Doe"
    assert created["url"] == "https://example.com/other"


async def test_a_capture_without_raw_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post("/captures/", json={}, headers=alice.headers)
    assert response.status_code == 422


async def test_a_blank_capture_is_rejected(client: AsyncClient, alice: Account) -> None:
    # A row nobody can recognise later is worse than a failed tap.
    for raw in ("", "   ", "\n\t "):
        response = await client.post("/captures/", json={"raw": raw}, headers=alice.headers)
        assert response.status_code == 422, raw


async def test_an_unknown_source_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/captures/", json={"raw": "Jane", "source": "telepathy"}, headers=alice.headers
    )
    assert response.status_code == 422


async def test_editing_raw_does_not_re_run_the_parser(client: AsyncClient, alice: Account) -> None:
    """By the time anyone edits, the name on the row is the corrected one."""
    created = await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})
    await client.patch(
        f"/captures/{created['id']}", json={"name": "Jane Doe-Smith"}, headers=alice.headers
    )
    patched = await client.patch(
        f"/captures/{created['id']}", json={"raw": "Someone Else"}, headers=alice.headers
    )
    assert patched.status_code == 200
    assert patched.json()["raw"] == "Someone Else"
    assert patched.json()["name"] == "Jane Doe-Smith"


async def test_status_cannot_be_set_through_patch(client: AsyncClient, alice: Account) -> None:
    """It moves through /convert and /dismiss or not at all."""
    created = await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})
    patched = await client.patch(
        f"/captures/{created['id']}", json={"status": "converted"}, headers=alice.headers
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "new"


async def test_the_inbox_is_oldest_first(client: AsyncClient, alice: Account) -> None:
    """A queue to empty, not a feed to scroll."""
    for name in ("first", "second", "third"):
        await create_resource(client, alice, "/captures/", {"raw": name})

    listed = await client.get("/captures/", headers=alice.headers)
    assert listed.status_code == 200
    assert [c["raw"] for c in listed.json()["items"]] == ["first", "second", "third"]


async def test_the_list_pages_and_reports_the_total(client: AsyncClient, alice: Account) -> None:
    for index in range(5):
        await create_resource(client, alice, "/captures/", {"raw": f"person {index}"})

    page = await client.get("/captures/?skip=2&limit=2", headers=alice.headers)
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 5
    assert [c["raw"] for c in body["items"]] == ["person 2", "person 3"]
    assert body["skip"] == 2
    assert body["limit"] == 2


async def test_the_list_refuses_a_nonsense_page(client: AsyncClient, alice: Account) -> None:
    for query in ("?limit=0", "?limit=500", "?skip=-1"):
        response = await client.get(f"/captures/{query}", headers=alice.headers)
        assert response.status_code == 422, query


async def test_search_matches_the_raw_text_as_well_as_the_name(
    client: AsyncClient, alice: Account
) -> None:
    # Half the rows have no name, so the raw line is all they can be found by.
    await create_resource(client, alice, "/captures/", {"raw": "https://example.com/acme/team"})
    await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})

    found = await client.get("/captures/?search=acme", headers=alice.headers)
    assert [c["raw"] for c in found.json()["items"]] == ["https://example.com/acme/team"]

    by_name = await client.get("/captures/?search=jane", headers=alice.headers)
    assert [c["name"] for c in by_name.json()["items"]] == ["Jane Doe"]


async def test_the_count_endpoint_answers_the_badge(client: AsyncClient, alice: Account) -> None:
    empty = await client.get("/captures/count", headers=alice.headers)
    assert empty.status_code == 200
    assert empty.json() == {"new": 0, "oldest_days": None}

    await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})
    await create_resource(client, alice, "/captures/", {"raw": "John Roe"})

    counted = await client.get("/captures/count", headers=alice.headers)
    assert counted.json()["new"] == 2
    # Just created, so not yet a day old.
    assert counted.json()["oldest_days"] == 0


async def test_the_count_route_is_not_swallowed_by_the_id_route(
    client: AsyncClient, alice: Account
) -> None:
    """Declaration order matters: /{capture_id} would 422 on "count"."""
    response = await client.get("/captures/count", headers=alice.headers)
    assert response.status_code == 200


async def test_another_tenants_capture_is_not_found(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    created = await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})

    assert (await client.get(f"/captures/{created['id']}", headers=bob.headers)).status_code == 404
    listed = await client.get("/captures/", headers=bob.headers)
    assert listed.json()["items"] == []
    assert (await client.get("/captures/count", headers=bob.headers)).json()["new"] == 0


async def test_status_all_widens_the_list(client: AsyncClient, alice: Account) -> None:
    """The "what did I do with that link?" question, not the daily one."""
    created = await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})
    await client.post(f"/captures/{created['id']}/dismiss", headers=alice.headers)

    default = await client.get("/captures/", headers=alice.headers)
    assert default.json()["items"] == []

    widened = await client.get("/captures/?status=all", headers=alice.headers)
    assert [c["raw"] for c in widened.json()["items"]] == ["Jane Doe"]

    dismissed = await client.get("/captures/?status=dismissed", headers=alice.headers)
    assert [c["raw"] for c in dismissed.json()["items"]] == ["Jane Doe"]


# --- Working a capture -------------------------------------------------------


async def _capture(client: AsyncClient, account: Account, raw: str = "Jane Doe") -> dict[str, Any]:
    return await create_resource(client, account, "/captures/", {"raw": raw})


async def test_converting_produces_a_contact_a_lead_and_a_logged_message(
    client: AsyncClient, alice: Account
) -> None:
    """The whole point of the feature, in one request."""
    capture = await _capture(client, alice, "Jane Doe https://linkedin.com/in/jane-doe")

    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={
            "contact": {"name": "Jane Doe", "email": "jane@example.com"},
            "deal": {"title": "Outreach - Jane Doe"},
            "interaction": {"kind": "email", "subject": "Wrote to Jane Doe"},
        },
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["contact"]["name"] == "Jane Doe"
    assert body["contact"]["lifecycle_status"] == "lead"
    assert body["deal"]["stage"] == "lead"
    assert body["deal"]["contact_id"] == body["contact"]["id"]
    assert body["interaction"]["subject"] == "Wrote to Jane Doe"
    # Logged now, so it already happened — otherwise tomorrow's briefing files
    # it under "planned, never confirmed".
    assert body["interaction"]["done"] is True
    assert body["interaction"]["contact_ids"] == [body["contact"]["id"]]
    assert body["interaction"]["deal_ids"] == [body["deal"]["id"]]

    assert body["capture"]["status"] == "converted"
    assert body["capture"]["triaged_at"] is not None
    assert body["capture"]["contact_id"] == body["contact"]["id"]
    assert body["capture"]["deal_id"] == body["deal"]["id"]
    assert body["capture"]["contact_name"] == "Jane Doe"
    assert body["capture"]["deal_title"] == "Outreach - Jane Doe"


async def test_a_converted_capture_leaves_the_inbox(client: AsyncClient, alice: Account) -> None:
    capture = await _capture(client, alice)
    await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe"}},
        headers=alice.headers,
    )

    inbox = await client.get("/captures/", headers=alice.headers)
    assert inbox.json()["items"] == []
    assert (await client.get("/captures/count", headers=alice.headers)).json()["new"] == 0


async def test_converting_can_link_an_existing_contact(client: AsyncClient, alice: Account) -> None:
    existing = await create_resource(client, alice, "/contacts/", {"name": "Jane Doe"})
    capture = await _capture(client, alice)

    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact_id": existing["id"], "deal": {"title": "Second approach"}},
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["contact"]["id"] == existing["id"]

    # No duplicate person was created.
    contacts = await client.get("/contacts/", headers=alice.headers)
    assert contacts.json()["total"] == 1


async def test_the_deal_and_the_message_are_both_optional(
    client: AsyncClient, alice: Account
) -> None:
    """Some captures are worth filing as a person and nothing more."""
    capture = await _capture(client, alice)
    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe"}},
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["deal"] is None
    assert response.json()["interaction"] is None
    assert response.json()["capture"]["deal_id"] is None


async def test_the_capture_source_carries_on_to_the_contact(
    client: AsyncClient, alice: Account
) -> None:
    capture = await create_resource(
        client, alice, "/captures/", {"raw": "Jane Doe", "source": "event"}
    )
    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe"}},
        headers=alice.headers,
    )
    assert response.json()["contact"]["source"] == "event"


async def test_the_body_can_override_the_captured_source(
    client: AsyncClient, alice: Account
) -> None:
    capture = await create_resource(
        client, alice, "/captures/", {"raw": "Jane Doe", "source": "event"}
    )
    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe", "source": "referral"}},
        headers=alice.headers,
    )
    assert response.json()["contact"]["source"] == "referral"


async def test_a_backdated_message_is_not_marked_done(client: AsyncClient, alice: Account) -> None:
    """A message planned for tomorrow has not happened yet."""
    capture = await _capture(client, alice)
    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={
            "contact": {"name": "Jane Doe"},
            "interaction": {
                "subject": "Follow up on Monday",
                "occurred_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
            },
        },
        headers=alice.headers,
    )
    assert response.json()["interaction"]["done"] is False


async def test_converting_needs_exactly_one_kind_of_contact(
    client: AsyncClient, alice: Account
) -> None:
    capture = await _capture(client, alice)
    existing = await create_resource(client, alice, "/contacts/", {"name": "Jane Doe"})

    neither = await client.post(
        f"/captures/{capture['id']}/convert", json={}, headers=alice.headers
    )
    assert neither.status_code == 422

    both = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact_id": existing["id"], "contact": {"name": "Jane Doe"}},
        headers=alice.headers,
    )
    assert both.status_code == 422


async def test_converting_twice_is_refused_and_changes_nothing(
    client: AsyncClient, alice: Account
) -> None:
    """The quiet duplicate this rule exists to prevent."""
    capture = await _capture(client, alice)
    first = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe"}, "deal": {"title": "Outreach"}},
        headers=alice.headers,
    )
    assert first.status_code == 201

    second = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe Again"}, "deal": {"title": "Outreach again"}},
        headers=alice.headers,
    )
    assert second.status_code == 409

    # No second person, no second deal, and the capture still points at the first.
    assert (await client.get("/contacts/", headers=alice.headers)).json()["total"] == 1
    assert (await client.get("/deals/", headers=alice.headers)).json()["total"] == 1
    unchanged = await client.get(f"/captures/{capture['id']}", headers=alice.headers)
    assert unchanged.json()["deal_id"] == first.json()["deal"]["id"]


async def test_a_dismissed_capture_cannot_be_converted(client: AsyncClient, alice: Account) -> None:
    capture = await _capture(client, alice)
    dismissed = await client.post(f"/captures/{capture['id']}/dismiss", headers=alice.headers)
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert dismissed.json()["triaged_at"] is not None

    response = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe"}},
        headers=alice.headers,
    )
    assert response.status_code == 409


async def test_dismissing_twice_is_refused(client: AsyncClient, alice: Account) -> None:
    capture = await _capture(client, alice)
    await client.post(f"/captures/{capture['id']}/dismiss", headers=alice.headers)
    again = await client.post(f"/captures/{capture['id']}/dismiss", headers=alice.headers)
    assert again.status_code == 409


async def test_converting_cannot_reach_another_tenants_rows(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    capture = await _capture(client, alice)
    bobs_contact = await create_resource(client, bob, "/contacts/", {"name": "Bob's contact"})
    bobs_org = await create_resource(client, bob, "/organizations/", {"name": "Bob's company"})

    borrowed_contact = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact_id": bobs_contact["id"]},
        headers=alice.headers,
    )
    assert borrowed_contact.status_code == 404

    borrowed_org = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe", "organization_id": bobs_org["id"]}},
        headers=alice.headers,
    )
    assert borrowed_org.status_code == 404

    # A refused convert leaves the capture waiting, not half-worked.
    still_new = await client.get(f"/captures/{capture['id']}", headers=alice.headers)
    assert still_new.json()["status"] == "new"


async def test_another_tenant_cannot_convert_or_dismiss(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    capture = await _capture(client, alice)
    convert = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Stolen"}},
        headers=bob.headers,
    )
    assert convert.status_code == 404
    dismiss = await client.post(f"/captures/{capture['id']}/dismiss", headers=bob.headers)
    assert dismiss.status_code == 404
