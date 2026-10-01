"""Deal stage timestamps and the stage-change log (T42, #115).

Nothing used to record when a deal last moved, so "how long has this been in
proposal?" had no answer. Two things answer it now:

*`stage_changed_at`* on the deal, for the age of the current stage. It moves
only when the stage does — PATCH routes every edit through `apply_stage`, and a
fixed typo must not make a stale deal look fresh.

*`deal_stage_events`*, append-only, for everything a single timestamp
overwrites: how many deals entered a stage this month, and how many of those
went on to the next one. A deal's creation is its first event.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from httpx2 import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.deal import Deal, DealStageEvent
from tests.conftest import Account, create_resource

Sessions = async_sessionmaker[AsyncSession]


async def _deal(client: AsyncClient, account: Account, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": "Website relaunch"}
    payload.update(fields)
    return await create_resource(client, account, "/deals/", payload)


async def _move(
    client: AsyncClient, account: Account, deal_id: str, stage: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"/deals/{deal_id}/stage", json={"stage": stage, **body}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    moved: dict[str, Any] = response.json()
    return moved


def _at(deal: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(deal["stage_changed_at"])


async def _events(session_factory: Sessions, deal_id: str) -> list[DealStageEvent]:
    async with session_factory() as session:
        result = await session.execute(
            select(DealStageEvent)
            .where(DealStageEvent.deal_id == UUID(deal_id))
            .order_by(DealStageEvent.changed_at)
        )
        return list(result.scalars().all())


async def test_a_new_deal_starts_its_clock_and_logs_its_first_stage(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice, stage="qualified")

    assert deal["stage_changed_at"] is not None
    [entered] = await _events(session_factory, deal["id"])
    # Entering the pipeline is entering a stage — a conversion rate that does
    # not count it starts from the wrong number.
    assert entered.from_stage is None
    assert entered.to_stage == "qualified"
    assert entered.changed_at == _at(deal)


async def test_an_edit_that_does_not_move_the_deal_leaves_the_clock_alone(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice, stage="proposal")

    retitled = await client.patch(
        f"/deals/{deal['id']}", json={"title": "Website relaunch, phase 1"}, headers=alice.headers
    )
    assert retitled.status_code == 200
    assert retitled.json()["stage_changed_at"] == deal["stage_changed_at"]

    # Sending the stage it already has is not a move either.
    same_stage = await client.patch(
        f"/deals/{deal['id']}", json={"stage": "proposal"}, headers=alice.headers
    )
    assert same_stage.json()["stage_changed_at"] == deal["stage_changed_at"]
    again = await _move(client, alice, deal["id"], "proposal")
    assert again["stage_changed_at"] == deal["stage_changed_at"]

    assert len(await _events(session_factory, deal["id"])) == 1


async def test_a_move_restarts_the_clock_and_writes_exactly_one_event(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice, stage="qualified")

    moved = await _move(client, alice, deal["id"], "proposal")

    assert _at(moved) > _at(deal)
    created, move = await _events(session_factory, deal["id"])
    assert created.to_stage == "qualified"
    assert (move.from_stage, move.to_stage) == ("qualified", "proposal")
    assert move.changed_at == _at(moved)


async def test_a_move_through_patch_is_recorded_the_same_way(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice)

    patched = await client.patch(
        f"/deals/{deal['id']}",
        json={"stage": "negotiation", "title": "Website relaunch, final"},
        headers=alice.headers,
    )

    assert _at(patched.json()) > _at(deal)
    events = await _events(session_factory, deal["id"])
    assert [(e.from_stage, e.to_stage) for e in events] == [
        (None, "lead"),
        ("lead", "negotiation"),
    ]


async def test_moving_back_adds_an_event_rather_than_editing_the_first(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice, stage="proposal")

    await _move(client, alice, deal["id"], "negotiation")
    back = await _move(client, alice, deal["id"], "proposal")

    events = await _events(session_factory, deal["id"])
    assert [(e.from_stage, e.to_stage) for e in events] == [
        (None, "proposal"),
        ("proposal", "negotiation"),
        ("negotiation", "proposal"),
    ]
    # The clock reflects re-entering proposal, not the first time round.
    assert _at(back) > _at(deal)


async def test_the_lost_reason_survives_in_the_log_after_a_reopen(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice, stage="proposal")

    await _move(client, alice, deal["id"], "lost", lost_reason="Went with an agency")
    reopened = await _move(client, alice, deal["id"], "proposal")

    # The deal forgets why it was lost once it is back in play; the log does not.
    assert reopened["lost_reason"] is None
    events = await _events(session_factory, deal["id"])
    assert [e.lost_reason for e in events] == [None, "Went with an agency", None]


async def test_deleting_a_deal_takes_its_history_with_it(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    deal = await _deal(client, alice)
    await _move(client, alice, deal["id"], "qualified")
    assert len(await _events(session_factory, deal["id"])) == 2

    deleted = await client.delete(f"/deals/{deal['id']}", headers=alice.headers)

    assert deleted.status_code == 204
    assert await _events(session_factory, deal["id"]) == []


async def test_deals_from_a_capture_or_a_watch_enter_the_pipeline_on_record(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    capture = await create_resource(client, alice, "/captures/", {"raw": "Jane Doe"})
    converted = await client.post(
        f"/captures/{capture['id']}/convert",
        json={"contact": {"name": "Jane Doe"}, "deal": {"title": "Outreach - Jane Doe"}},
        headers=alice.headers,
    )
    assert converted.status_code == 201, converted.text

    watch = await create_resource(
        client,
        alice,
        "/watches/",
        {"name": "TED", "url": "https://ted.europa.eu", "recurrence_rule": "weekly"},
    )
    checked = await client.post(
        f"/watches/{watch['id']}/check",
        json={"outcome": "found", "create_deal": {"title": "Rahmenvertrag"}},
        headers=alice.headers,
    )
    assert checked.status_code == 201, checked.text

    for deal_id in (converted.json()["deal"]["id"], checked.json()["check"]["created_deal_id"]):
        deal = (await client.get(f"/deals/{deal_id}", headers=alice.headers)).json()
        assert deal["stage"] == "lead"
        assert deal["stage_changed_at"] is not None
        [entered] = await _events(session_factory, deal_id)
        assert (entered.from_stage, entered.to_stage) == (None, "lead")


async def test_the_list_can_put_the_longest_waiting_deals_first(
    client: AsyncClient, alice: Account, session_factory: Sessions
) -> None:
    fresh = await _deal(client, alice, title="Fresh", expected_close_date="2026-10-15")
    stale = await _deal(client, alice, title="Stale", expected_close_date="2026-12-31")
    middle = await _deal(client, alice, title="Middle")

    now = datetime.now(UTC)
    async with session_factory() as session:
        for deal, age in ((stale, 90), (middle, 30), (fresh, 1)):
            await session.execute(
                update(Deal)
                .where(Deal.id == UUID(deal["id"]))
                .values(stage_changed_at=now - timedelta(days=age))
            )
        await session.commit()

    by_age = await client.get("/deals/?sort=stage_changed_at", headers=alice.headers)
    assert by_age.status_code == 200
    assert [d["title"] for d in by_age.json()["items"]] == ["Stale", "Middle", "Fresh"]

    # The default order is untouched: soonest close first, undated last.
    default = await client.get("/deals/", headers=alice.headers)
    assert [d["title"] for d in default.json()["items"]] == ["Fresh", "Stale", "Middle"]

    assert (await client.get("/deals/?sort=title", headers=alice.headers)).status_code == 422
