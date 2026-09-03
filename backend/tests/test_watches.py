"""The watch list: sources swept on a cadence, and the log of every sweep.

The intake end of the pipeline — the job boards, careers pages and tender
portals checked regularly, before there is any conversation to record.

Three things here are not plain CRUD:

*The cadence reuses `app/recurrence.py`.* A source swept three weeks late is due
once, not three times, because the next due date is anchored on the check rather
than on the missed slot — the same rule recurring tasks already follow.

*The log is append-only.* "Nothing found" is a valuable answer: it is what makes
a year of diligence on a quiet portal provable, and what separates a source that
has produced nothing from one nobody has ever checked.

*A find converts in one call.* Logging the sweep, advancing the cadence and
creating the deal it produced all commit together, or the check comes straight
back as due with a deal nothing points at.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def _watch(client: AsyncClient, account: Account, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "TED tenders",
        "url": "https://ted.europa.eu/search",
        "kind": "tender_portal",
        "recurrence_rule": "weekly",
    }
    payload.update(fields)
    return await create_resource(client, account, "/watches/", payload)


async def _check(
    client: AsyncClient, account: Account, watch_id: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(f"/watches/{watch_id}/check", json=body, headers=account.headers)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


# --- The source itself ------------------------------------------------------


async def test_a_watch_survives_a_full_round_trip(client: AsyncClient, alice: Account) -> None:
    created = await _watch(
        client,
        alice,
        name="ANKÖ",
        url="https://ankoe.at/suche",
        kind="tender_portal",
        query_note="CPV 72000, Wien + NÖ, ab 50k",
        recurrence_rule="weekly",
        recurrence_interval=1,
        notes="Login required.",
    )
    assert created["kind"] == "tender_portal"
    # The saved search in words — a query string is unreadable six months on.
    assert created["query_note"] == "CPV 72000, Wien + NÖ, ab 50k"
    assert created["active"] is True
    assert created["last_checked_at"] is None
    assert created["found_count"] == 0
    assert created["check_count"] == 0

    fetched = await client.get(f"/watches/{created['id']}", headers=alice.headers)
    assert fetched.status_code == 200
    assert fetched.json()["url"] == "https://ankoe.at/suche"

    patched = await client.patch(
        f"/watches/{created['id']}", json={"name": "ANKÖ (Vergabeportal)"}, headers=alice.headers
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "ANKÖ (Vergabeportal)"

    deleted = await client.delete(f"/watches/{created['id']}", headers=alice.headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/watches/{created['id']}", headers=alice.headers)).status_code == 404


async def test_a_new_source_is_due_immediately(client: AsyncClient, alice: Account) -> None:
    # A source nobody has swept yet belongs in the first "what's due today",
    # not hidden for a cadence.
    created = await _watch(client, alice)

    assert created["next_due_at"] is not None
    due_now = await client.get("/watches/?due=true", headers=alice.headers)
    assert due_now.json()["total"] == 1


async def test_a_watch_can_start_already_checked(client: AsyncClient, alice: Account) -> None:
    # Added right after checking the site by hand — do not demand a second sweep.
    later = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    await _watch(client, alice, next_due_at=later)

    assert (await client.get("/watches/?due=true", headers=alice.headers)).json()["total"] == 0


async def test_a_watch_needs_a_cadence_and_a_url(client: AsyncClient, alice: Account) -> None:
    for payload in (
        {"name": "X", "url": "https://x.example"},  # no rule
        {"name": "X", "recurrence_rule": "weekly"},  # no url
        {"name": "X", "url": "https://x.example", "recurrence_rule": "fortnightly"},
        {"name": "X", "url": "https://x.example", "recurrence_rule": "weekly", "kind": "rss"},
        {
            "name": "X",
            "url": "https://x.example",
            "recurrence_rule": "weekly",
            "recurrence_interval": 0,
        },
    ):
        response = await client.post("/watches/", json=payload, headers=alice.headers)
        assert response.status_code == 422, f"{payload} should be refused"


async def test_a_careers_page_links_to_its_company(client: AsyncClient, alice: Account) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "EBCONT"})

    created = await _watch(
        client,
        alice,
        name="EBCONT careers",
        url="https://ebcont.com/jobs",
        kind="careers_page",
        organization_id=organization["id"],
    )

    assert created["organization_id"] == organization["id"]
    # Denormalised so a list row shows the company without a second request.
    assert created["organization_name"] == "EBCONT"


async def test_a_portal_needs_no_company(client: AsyncClient, alice: Account) -> None:
    # The whole reason this is not three columns on `organizations`: a job board
    # and a tender portal are sources, not parties.
    created = await _watch(client, alice, kind="job_board", name="karriere.at")

    assert created["organization_id"] is None
    assert created["organization_name"] is None


async def test_losing_the_company_keeps_the_watch(client: AsyncClient, alice: Account) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "EBCONT"})
    created = await _watch(client, alice, kind="careers_page", organization_id=organization["id"])

    assert (
        await client.delete(f"/organizations/{organization['id']}", headers=alice.headers)
    ).status_code == 204

    # The careers page is still worth checking.
    survivor = await client.get(f"/watches/{created['id']}", headers=alice.headers)
    assert survivor.status_code == 200
    assert survivor.json()["organization_id"] is None


async def test_a_watch_cannot_point_at_another_users_company(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    alices = await create_resource(client, alice, "/organizations/", {"name": "ACME"})

    created = await client.post(
        "/watches/",
        json={
            "name": "X",
            "url": "https://x.example",
            "recurrence_rule": "weekly",
            "organization_id": alices["id"],
        },
        headers=bob.headers,
    )
    assert created.status_code == 404

    bobs = await _watch(client, bob)
    patched = await client.patch(
        f"/watches/{bobs['id']}", json={"organization_id": alices["id"]}, headers=bob.headers
    )
    assert patched.status_code == 404


# --- Sweeping ---------------------------------------------------------------


async def test_a_sweep_that_found_nothing_still_counts(client: AsyncClient, alice: Account) -> None:
    watch = await _watch(client, alice)

    result = await _check(client, alice, watch["id"], outcome="nothing")

    assert result["check"]["outcome"] == "nothing"
    assert result["watch"]["last_checked_at"] is not None
    assert result["watch"]["check_count"] == 1
    # Nothing found is not nothing recorded.
    assert result["watch"]["found_count"] == 0
    # And it is no longer due.
    assert (await client.get("/watches/?due=true", headers=alice.headers)).json()["total"] == 0


async def test_the_cadence_advances_by_the_rule(client: AsyncClient, alice: Account) -> None:
    watch = await _watch(client, alice, recurrence_rule="weekly", recurrence_interval=1)
    checked_at = datetime.now(UTC)

    result = await _check(client, alice, watch["id"], checked_at=checked_at.isoformat())

    next_due = datetime.fromisoformat(result["watch"]["next_due_at"])
    # A week out, give or take the second the request took.
    assert timedelta(days=6, hours=23) < next_due - checked_at < timedelta(days=7, hours=1)


async def test_a_late_sweep_is_due_once_not_for_every_missed_slot(
    client: AsyncClient, alice: Account
) -> None:
    # The rule recurring tasks already follow: re-anchor on the check rather
    # than walking the missed slots forward, so three weeks away yields one
    # sweep to do, not three.
    long_ago = (datetime.now(UTC) - timedelta(days=21)).isoformat()
    watch = await _watch(client, alice, recurrence_rule="weekly", next_due_at=long_ago)

    now = datetime.now(UTC)
    result = await _check(client, alice, watch["id"], checked_at=now.isoformat())

    next_due = datetime.fromisoformat(result["watch"]["next_due_at"])
    assert next_due > now, "a late sweep must not leave the watch still overdue"
    assert next_due - now < timedelta(days=8)


async def test_the_history_is_append_only_and_newest_first(
    client: AsyncClient, alice: Account
) -> None:
    watch = await _watch(client, alice)
    for days_ago, outcome in ((21, "nothing"), (14, "found"), (7, "nothing")):
        await _check(
            client,
            alice,
            watch["id"],
            outcome=outcome,
            note=f"sweep {days_ago}",
            checked_at=(datetime.now(UTC) - timedelta(days=days_ago)).isoformat(),
        )

    history = await client.get(f"/watches/{watch['id']}/checks", headers=alice.headers)

    assert history.status_code == 200
    assert history.json()["total"] == 3
    assert [c["note"] for c in history.json()["items"]] == ["sweep 7", "sweep 14", "sweep 21"]
    # The question a single timestamp cannot answer: has this ever produced
    # anything?
    detail = await client.get(f"/watches/{watch['id']}", headers=alice.headers)
    assert detail.json()["check_count"] == 3
    assert detail.json()["found_count"] == 1


async def test_a_find_becomes_a_deal_in_one_call(client: AsyncClient, alice: Account) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "Stadt Wien"})
    watch = await _watch(client, alice, kind="tender_portal", organization_id=organization["id"])

    result = await _check(
        client,
        alice,
        watch["id"],
        outcome="found",
        note="IT-DL Rahmenvertrag, CPV 72000",
        create_deal={"title": "IT-DL Rahmenvertrag", "expected_close_date": "2026-09-30"},
    )

    deal_id = result["check"]["created_deal_id"]
    assert deal_id is not None
    deal = await client.get(f"/deals/{deal_id}", headers=alice.headers)
    assert deal.status_code == 200
    assert deal.json()["title"] == "IT-DL Rahmenvertrag"
    assert deal.json()["expected_close_date"] == "2026-09-30"
    # The watch's own company is the obvious default for a portal already filed
    # against a contracting authority.
    assert deal.json()["organization_id"] == organization["id"]


async def test_a_find_becomes_a_task_in_one_call(client: AsyncClient, alice: Account) -> None:
    watch = await _watch(client, alice, kind="job_board", name="karriere.at")
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()

    result = await _check(
        client,
        alice,
        watch["id"],
        outcome="found",
        note="Cloud Engineer at EBCONT",
        create_task={"title": "Approach EBCONT about the Cloud Engineer role", "due_date": due},
    )

    task_id = result["check"]["created_task_id"]
    assert task_id is not None
    task = await client.get(f"/tasks/{task_id}", headers=alice.headers)
    assert task.status_code == 200
    assert task.json()["title"] == "Approach EBCONT about the Cloud Engineer role"


async def test_creating_something_from_a_sweep_that_found_nothing_is_refused(
    client: AsyncClient, alice: Account
) -> None:
    watch = await _watch(client, alice)

    response = await client.post(
        f"/watches/{watch['id']}/check",
        json={"outcome": "nothing", "create_deal": {"title": "X"}},
        headers=alice.headers,
    )

    assert response.status_code == 422
    # And nothing was logged or created on the way out.
    assert (await client.get(f"/watches/{watch['id']}/checks", headers=alice.headers)).json()[
        "total"
    ] == 0
    assert (await client.get("/deals/", headers=alice.headers)).json()["total"] == 0


async def test_a_refused_find_creates_neither_deal_nor_check(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    # The whole call commits or nothing does — a deal filed against another
    # tenant's company must not leave a check behind.
    alices = await create_resource(client, alice, "/organizations/", {"name": "ACME"})
    watch = await _watch(client, bob)

    response = await client.post(
        f"/watches/{watch['id']}/check",
        json={
            "outcome": "found",
            "create_deal": {"title": "Bob's find", "organization_id": alices["id"]},
        },
        headers=bob.headers,
    )

    assert response.status_code == 404
    assert (await client.get(f"/watches/{watch['id']}/checks", headers=bob.headers)).json()[
        "total"
    ] == 0
    assert (await client.get("/deals/", headers=bob.headers)).json()["total"] == 0
    # The cadence did not move either.
    assert (await client.get(f"/watches/{watch['id']}", headers=bob.headers)).json()[
        "last_checked_at"
    ] is None


async def test_deleting_the_deal_keeps_the_record_of_finding_it(
    client: AsyncClient, alice: Account
) -> None:
    watch = await _watch(client, alice)
    result = await _check(
        client,
        alice,
        watch["id"],
        outcome="found",
        note="Worth remembering even if the deal dies",
        create_deal={"title": "A find"},
    )
    deal_id = result["check"]["created_deal_id"]

    assert (await client.delete(f"/deals/{deal_id}", headers=alice.headers)).status_code == 204

    history = await client.get(f"/watches/{watch['id']}/checks", headers=alice.headers)
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["note"] == "Worth remembering even if the deal dies"
    assert history.json()["items"][0]["created_deal_id"] is None


async def test_deleting_a_watch_takes_its_history(client: AsyncClient, alice: Account) -> None:
    watch = await _watch(client, alice)
    await _check(client, alice, watch["id"])

    assert (
        await client.delete(f"/watches/{watch['id']}", headers=alice.headers)
    ).status_code == 204

    # The log is part of the watch, so the checks go with it — pausing is the
    # non-destructive option.
    assert (
        await client.get(f"/watches/{watch['id']}/checks", headers=alice.headers)
    ).status_code == 404


async def test_the_check_endpoint_is_owner_only(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    watch = await _watch(client, alice)

    assert (
        await client.post(f"/watches/{watch['id']}/check", json={}, headers=bob.headers)
    ).status_code == 404
    assert (await client.post(f"/watches/{watch['id']}/check", json={})).status_code == 401
    assert (
        await client.get(f"/watches/{watch['id']}/checks", headers=bob.headers)
    ).status_code == 404
    assert (await client.get(f"/watches/{watch['id']}", headers=alice.headers)).json()[
        "last_checked_at"
    ] is None


# --- Finding them again -----------------------------------------------------


async def test_the_sweep_list_is_most_overdue_first(client: AsyncClient, alice: Account) -> None:
    now = datetime.now(UTC)
    await _watch(
        client, alice, name="Least overdue", next_due_at=(now - timedelta(days=1)).isoformat()
    )
    await _watch(
        client, alice, name="Most overdue", next_due_at=(now - timedelta(days=30)).isoformat()
    )
    await _watch(
        client, alice, name="Not yet due", next_due_at=(now + timedelta(days=5)).isoformat()
    )

    due = await client.get("/watches/?due=true", headers=alice.headers)

    assert [w["name"] for w in due.json()["items"]] == ["Most overdue", "Least overdue"]
    # The order the sweep is actually worked in, across the whole list too.
    everything = await client.get("/watches/", headers=alice.headers)
    assert [w["name"] for w in everything.json()["items"]] == [
        "Most overdue",
        "Least overdue",
        "Not yet due",
    ]


async def test_a_paused_source_sinks_and_can_be_filtered_out(
    client: AsyncClient, alice: Account
) -> None:
    now = datetime.now(UTC)
    await _watch(client, alice, name="Running", next_due_at=(now - timedelta(days=1)).isoformat())
    paused = await _watch(
        client, alice, name="Paused", next_due_at=(now - timedelta(days=90)).isoformat()
    )
    await client.patch(f"/watches/{paused['id']}", json={"active": False}, headers=alice.headers)

    everything = await client.get("/watches/", headers=alice.headers)
    # Ninety days "overdue" while paused must not head the list.
    assert [w["name"] for w in everything.json()["items"]] == ["Running", "Paused"]

    active_only = await client.get("/watches/?active=true", headers=alice.headers)
    assert active_only.json()["total"] == 1
    assert active_only.json()["items"][0]["name"] == "Running"


@pytest.mark.parametrize("kind", ["job_board", "careers_page", "tender_portal", "other"])
async def test_sources_can_be_filtered_by_kind(
    kind: str, client: AsyncClient, alice: Account
) -> None:
    for k in ("job_board", "careers_page", "tender_portal", "other"):
        await _watch(client, alice, name=f"A {k}", kind=k)

    response = await client.get(f"/watches/?kind={kind}", headers=alice.headers)

    assert response.json()["total"] == 1
    assert response.json()["items"][0]["kind"] == kind


async def test_sources_can_be_searched_and_filtered_by_company(
    client: AsyncClient, alice: Account
) -> None:
    organization = await create_resource(client, alice, "/organizations/", {"name": "EBCONT"})
    await _watch(
        client,
        alice,
        name="EBCONT careers",
        kind="careers_page",
        organization_id=organization["id"],
    )
    await _watch(client, alice, name="karriere.at", kind="job_board")

    by_name = await client.get("/watches/?search=karriere", headers=alice.headers)
    assert by_name.json()["total"] == 1

    by_org = await client.get(
        f"/watches/?organization_id={organization['id']}", headers=alice.headers
    )
    assert by_org.json()["total"] == 1
    assert by_org.json()["items"][0]["name"] == "EBCONT careers"


async def test_changing_the_cadence_reschedules_a_checked_source(
    client: AsyncClient, alice: Account
) -> None:
    watch = await _watch(client, alice, recurrence_rule="monthly")
    checked_at = datetime.now(UTC)
    await _check(client, alice, watch["id"], checked_at=checked_at.isoformat())

    switched = await client.patch(
        f"/watches/{watch['id']}", json={"recurrence_rule": "weekly"}, headers=alice.headers
    )

    # Switching monthly to weekly must not leave it on the monthly schedule.
    next_due = datetime.fromisoformat(switched.json()["next_due_at"])
    assert next_due - checked_at < timedelta(days=8)


async def test_changing_the_cadence_leaves_an_unswept_source_due(
    client: AsyncClient, alice: Account
) -> None:
    # It has still never been checked, whatever its cadence now is — editing it
    # must not push a brand new source out of "due today".
    watch = await _watch(client, alice, recurrence_rule="weekly")

    await client.patch(
        f"/watches/{watch['id']}", json={"recurrence_rule": "monthly"}, headers=alice.headers
    )

    assert (await client.get("/watches/?due=true", headers=alice.headers)).json()["total"] == 1


async def test_a_bad_page_size_is_rejected(client: AsyncClient, alice: Account) -> None:
    assert (await client.get("/watches/?limit=0", headers=alice.headers)).status_code == 422
    assert (await client.get("/watches/?limit=500", headers=alice.headers)).status_code == 422
    assert (await client.get("/watches/?skip=-1", headers=alice.headers)).status_code == 422
