"""GET /metrics/dashboard (#138): the arithmetic, the windows and the tenancy.

Rows are written straight through the models, as in test_briefing.py: what
matters is *when* things fall relative to a period boundary in the operator's
timezone, and stage events with chosen timestamps cannot be made through the
API, which stamps them with the real clock.

The clock is pinned to 07:00 Berlin time on Friday 4 September 2026, so the
quarter is Q3 (1 July – 1 October), the month September and the week the one
starting Monday 31 August.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx2 import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.main import app
from app.metrics import Period
from app.models import Capture, Deal, DealStageEvent, Interaction, Task
from app.routers.briefing import current_time
from tests.conftest import Account

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 9, 4, 7, 0, tzinfo=BERLIN)

Sessions = async_sessionmaker[AsyncSession]


def berlin(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=BERLIN)


async def _seed(session_factory: Sessions, *rows: Any) -> None:
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()


def _deal(
    account: Account,
    title: str,
    stage: str = "lead",
    *,
    value: str | None = "1000.00",
    since: datetime = berlin("2026-09-01T09:00"),
    **fields: Any,
) -> Deal:
    """A fixed-price deal by default; `value=None` makes it open-ended — a day
    rate with no volume estimate, so no total can be derived."""
    if value is None:
        fields.update(value_type="rate_based", rate=Decimal("800.00"), rate_unit="day")
    else:
        fields.update(value_type="fixed", fixed_value=Decimal(value))
    fields.setdefault("created_at", since)
    return Deal(user_id=account.id, title=title, stage=stage, stage_changed_at=since, **fields)


def _event(deal: Deal, to_stage: str, at: datetime, from_stage: str | None = None) -> None:
    deal.stage_events.add(DealStageEvent(from_stage=from_stage, to_stage=to_stage, changed_at=at))


@pytest.fixture
def pinned_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    monkeypatch.setattr(settings, "briefing_timezone", "Europe/Berlin")

    def pin(moment: datetime) -> None:
        app.dependency_overrides[current_time] = lambda: moment

    pin(NOW)
    return pin


async def _metrics(
    client: AsyncClient, account: Account, period: str = "quarter"
) -> dict[str, Any]:
    response = await client.get(
        "/metrics/dashboard", params={"period": period}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- The endpoint and its period ---------------------------------------------


async def test_the_dashboard_needs_a_login(client: AsyncClient) -> None:
    response = await client.get("/metrics/dashboard")
    assert response.status_code == 401


async def test_an_unknown_period_is_refused(
    client: AsyncClient, alice: Account, pinned_clock: Callable[[datetime], None]
) -> None:
    response = await client.get(
        "/metrics/dashboard", params={"period": "fortnight"}, headers=alice.headers
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("period", "start", "end"),
    [
        ("week", "2026-08-31", "2026-09-07"),
        ("month", "2026-09-01", "2026-10-01"),
        ("quarter", "2026-07-01", "2026-10-01"),
        ("year", "2026-01-01", "2027-01-01"),
    ],
)
async def test_the_period_is_echoed_back_resolved(
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
    period: str,
    start: str,
    end: str,
) -> None:
    body = await _metrics(client, alice, period)
    assert body["period"] == {
        "kind": period,
        "start": start,
        "end": end,
        "timezone": "Europe/Berlin",
        "today": "2026-09-04",
    }


async def test_quarter_is_the_default(
    client: AsyncClient, alice: Account, pinned_clock: Callable[[datetime], None]
) -> None:
    response = await client.get("/metrics/dashboard", headers=alice.headers)
    assert response.json()["period"]["kind"] == "quarter"


async def test_the_period_turns_at_local_midnight_not_utc(
    client: AsyncClient, alice: Account, pinned_clock: Callable[[datetime], None]
) -> None:
    # 00:30 on 1 October in Berlin is still 30 September in UTC.
    pinned_clock(berlin("2026-10-01T00:30"))
    body = await _metrics(client, alice)
    assert body["period"]["start"] == "2026-10-01"
    assert body["period"]["end"] == "2027-01-01"


def test_period_bounds_carry_their_own_offset_across_a_dst_switch() -> None:
    # Q4 starts in summer time and ends in winter time: Berlin midnight is
    # 22:00Z on 30 September and 23:00Z on 31 December.
    period = Period.containing("quarter", berlin("2026-11-15T12:00"), BERLIN)
    assert period.start == berlin("2026-10-01T00:00")
    assert period.end == berlin("2027-01-01T00:00")
    assert period.start.utcoffset() != period.end.utcoffset()
    assert period.day.today == date(2026, 11, 15)


# --- A · Pipeline ------------------------------------------------------------


async def test_pipeline_groups_by_stage_and_currency_and_counts_open_ended_deals(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(
        session_factory,
        _deal(alice, "Bid A", "proposal", value="30000.00"),
        _deal(alice, "Bid B", "proposal", value="18000.50"),
        _deal(alice, "Day rate, no estimate", "proposal", value=None),
        _deal(alice, "US bid", "proposal", value="12000.00", currency="USD"),
        _deal(alice, "Fresh", "lead", value=None),
        # Not in play: decided or finished.
        _deal(alice, "Done", "completed", value="99999.00"),
        _deal(alice, "Gone", "lost", value="99999.00"),
        # Committed, not delivered.
        _deal(alice, "Won", "won", value="20000.00"),
        _deal(alice, "Running", "running", value=None),
    )

    pipeline = (await _metrics(client, alice))["pipeline"]

    assert pipeline["by_stage"] == [
        {"stage": "lead", "currency": "EUR", "count": 1, "value": "0.00", "open_ended": 1},
        {"stage": "proposal", "currency": "EUR", "count": 3, "value": "48000.50", "open_ended": 1},
        {"stage": "proposal", "currency": "USD", "count": 1, "value": "12000.00", "open_ended": 0},
    ]
    assert pipeline["committed"] == [
        {"currency": "EUR", "count": 2, "value": "20000.00", "open_ended": 1},
    ]
    assert "weighted" not in pipeline


async def test_groups_that_cannot_be_computed_yet_are_absent(
    client: AsyncClient, alice: Account, pinned_clock: Callable[[datetime], None]
) -> None:
    body = await _metrics(client, alice)
    assert set(body) == {"period", "pipeline", "velocity", "attention", "activity", "trends"}


# --- B · Velocity ------------------------------------------------------------


async def test_velocity_reports_median_age_and_the_oldest_deal_per_stage(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(
        session_factory,
        # 2, 10 and 30 calendar days in proposal. 23:30 on the 2nd is two days
        # ago in Berlin even though it is under 32 hours.
        _deal(alice, "Recent", "proposal", since=berlin("2026-09-02T23:30")),
        _deal(alice, "Middle", "proposal", since=berlin("2026-08-25T10:00")),
        _deal(alice, "Parked", "proposal", since=berlin("2026-08-05T10:00")),
        _deal(alice, "Lead A", "lead", since=berlin("2026-09-03T10:00")),
        _deal(alice, "Lead B", "lead", since=berlin("2026-09-01T10:00")),
        _deal(alice, "Won", "won", since=berlin("2026-01-01T10:00")),
    )

    by_stage = (await _metrics(client, alice))["velocity"]["by_stage"]

    assert [(s["stage"], s["count"], s["median_days_in_stage"]) for s in by_stage] == [
        ("lead", 2, 2.0),
        ("proposal", 3, 10.0),
    ]
    oldest = by_stage[1]["oldest"]
    assert oldest["title"] == "Parked"
    assert oldest["days_in_stage"] == 30


async def test_deals_entering_a_stage_are_counted_within_the_local_period(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    moved = _deal(alice, "Moved", "proposal")
    # Q2 locally: outside.
    _event(moved, "lead", berlin("2026-06-30T23:30"))
    # Q3 locally, though it is still 30 June in UTC: inside.
    _event(moved, "qualified", berlin("2026-07-01T00:30"), "lead")
    _event(moved, "proposal", berlin("2026-08-10T10:00"), "qualified")
    # Back and forth: still one deal entering proposal.
    _event(moved, "qualified", berlin("2026-08-11T10:00"), "proposal")
    _event(moved, "proposal", berlin("2026-08-12T10:00"), "qualified")
    other = _deal(alice, "Other", "won")
    _event(other, "proposal", berlin("2026-09-01T10:00"))
    _event(other, "won", berlin("2026-09-03T10:00"), "proposal")
    await _seed(session_factory, moved, other)

    entered = (await _metrics(client, alice))["velocity"]["entered"]

    assert entered == [
        {"stage": "qualified", "count": 1},
        {"stage": "proposal", "count": 2},
        {"stage": "won", "count": 1},
    ]


async def test_conversion_counts_deals_that_went_further_and_not_lost_ones(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    # Skipped qualified: advanced out of lead all the same.
    skipper = _deal(alice, "Skipper", "proposal")
    _event(skipper, "lead", berlin("2026-08-01T10:00"))
    _event(skipper, "proposal", berlin("2026-08-02T10:00"), "lead")
    # Lost from lead: entered, did not advance.
    lost = _deal(alice, "Lost", "lost")
    _event(lost, "lead", berlin("2026-08-01T10:00"))
    _event(lost, "lost", berlin("2026-08-05T10:00"), "lead")
    # Won from negotiation.
    winner = _deal(alice, "Winner", "won")
    _event(winner, "lead", berlin("2026-08-01T10:00"))
    _event(winner, "negotiation", berlin("2026-08-10T10:00"), "lead")
    _event(winner, "won", berlin("2026-08-20T10:00"), "negotiation")
    # Still sitting in lead.
    waiting = _deal(alice, "Waiting", "lead")
    _event(waiting, "lead", berlin("2026-08-01T10:00"))
    await _seed(session_factory, skipper, lost, winner, waiting)

    conversion = (await _metrics(client, alice))["velocity"]["conversion"]

    assert conversion == [
        {"stage": "lead", "entered": 4, "advanced": 2},
        {"stage": "qualified", "entered": 0, "advanced": 0},
        {"stage": "proposal", "entered": 1, "advanced": 0},
        {"stage": "negotiation", "entered": 1, "advanced": 1},
    ]


async def test_sales_cycle_is_the_median_from_opening_to_first_win_in_the_period(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    fast = _deal(alice, "Fast", "won", created_at=berlin("2026-08-01T10:00"))
    _event(fast, "won", berlin("2026-08-11T10:00"))  # 10 days
    slow = _deal(alice, "Slow", "running", created_at=berlin("2026-05-01T10:00"))
    _event(slow, "won", berlin("2026-07-31T10:00"))  # 91 days
    _event(slow, "running", berlin("2026-08-15T10:00"), "won")
    middle = _deal(alice, "Middle", "won", created_at=berlin("2026-07-01T10:00"))
    _event(middle, "won", berlin("2026-08-10T10:00"))  # 40 days
    # Won last quarter: outside the window.
    earlier = _deal(alice, "Earlier", "completed", created_at=berlin("2026-03-01T10:00"))
    _event(earlier, "won", berlin("2026-06-01T10:00"))
    await _seed(session_factory, fast, slow, middle, earlier)

    cycle = (await _metrics(client, alice))["velocity"]["sales_cycle"]
    assert cycle == {"deals": 3, "median_days": 40.0}


async def test_an_empty_pipeline_has_no_medians_rather_than_zeros(
    client: AsyncClient, alice: Account, pinned_clock: Callable[[datetime], None]
) -> None:
    velocity = (await _metrics(client, alice))["velocity"]
    assert velocity["by_stage"] == []
    assert velocity["sales_cycle"] == {"deals": 0, "median_days": None}


# --- D · Attention -----------------------------------------------------------


async def test_attention_counts_match_the_briefing_and_link_to_their_lists(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(
        session_factory,
        # Stalled: open, no next step.
        _deal(alice, "Quiet", "proposal"),
        # Overdue: expected close yesterday. Today is not overdue yet.
        _deal(alice, "Expired", "negotiation", expected_close_date=date(2026, 9, 3)),
        _deal(alice, "Closing today", "negotiation", expected_close_date=date(2026, 9, 4)),
        _deal(alice, "Won late", "won", expected_close_date=date(2026, 8, 1)),
        Task(user_id=alice.id, title="Slipped", due_date=berlin("2026-09-03T23:59")),
        Task(user_id=alice.id, title="Tonight", due_date=berlin("2026-09-04T23:59")),
        Interaction(
            user_id=alice.id, subject="Never confirmed", occurred_at=berlin("2026-09-01T10:00")
        ),
        Capture(user_id=alice.id, raw="Jane", name="Jane", created_at=berlin("2026-08-26T09:00")),
        Capture(user_id=alice.id, raw="John", name="John", created_at=berlin("2026-09-03T09:00")),
        Capture(user_id=alice.id, raw="Done", name="Done", status="dismissed"),
    )

    attention = (await _metrics(client, alice))["attention"]

    assert attention == {
        "stalled_deals": {
            "count": 3,
            "list": {"path": "/deals/", "params": {"stalled": "true"}, "field": None},
            "oldest_days": None,
        },
        "overdue_deals": {
            "count": 1,
            "list": {"path": "/deals/", "params": {"overdue": "true"}, "field": None},
            "oldest_days": None,
        },
        "overdue_tasks": {
            "count": 1,
            "list": {"path": "/briefing/", "params": {}, "field": "overdue_tasks"},
            "oldest_days": None,
        },
        "unconfirmed_interactions": {
            "count": 1,
            "list": {"path": "/briefing/", "params": {}, "field": "unconfirmed_interactions"},
            "oldest_days": None,
        },
        "captures_waiting": {
            "count": 2,
            "list": {"path": "/captures/", "params": {"status": "new"}, "field": None},
            "oldest_days": 9,
        },
    }


async def test_the_overdue_filter_lists_what_the_dashboard_counts(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    bob: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(
        session_factory,
        _deal(alice, "Long expired", "proposal", expected_close_date=date(2026, 7, 1)),
        _deal(alice, "Expired", "negotiation", expected_close_date=date(2026, 9, 3)),
        _deal(alice, "Closing today", "negotiation", expected_close_date=date(2026, 9, 4)),
        _deal(alice, "No date", "lead"),
        _deal(alice, "Lost late", "lost", expected_close_date=date(2026, 8, 1)),
        _deal(bob, "Bob's", "proposal", expected_close_date=date(2026, 8, 1)),
    )

    response = await client.get("/deals/", params={"overdue": "true"}, headers=alice.headers)

    assert response.status_code == 200
    page = response.json()
    # Furthest past first.
    assert [d["title"] for d in page["items"]] == ["Long expired", "Expired"]
    assert page["total"] == (await _metrics(client, alice))["attention"]["overdue_deals"]["count"]


async def test_overdue_uses_the_local_day(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(
        session_factory,
        _deal(alice, "Due the 4th", "proposal", expected_close_date=date(2026, 9, 4)),
    )
    # 23:30Z on the 4th is already the 5th in Berlin.
    pinned_clock(datetime.fromisoformat("2026-09-04T23:30+00:00"))
    response = await client.get("/deals/", params={"overdue": "true"}, headers=alice.headers)
    assert response.json()["total"] == 1


# --- E · Activity ------------------------------------------------------------


async def test_activity_counts_what_happened_in_the_period(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    def done(subject: str, kind: str, at: str) -> Interaction:
        return Interaction(
            user_id=alice.id, subject=subject, kind=kind, occurred_at=berlin(at), done=True
        )

    await _seed(
        session_factory,
        done("Call 1", "call", "2026-09-01T10:00"),
        done("Call 2", "call", "2026-09-03T10:00"),
        done("Mail", "email", "2026-08-31T00:15"),  # Monday 00:15 local: this week.
        done("Sunday mail", "email", "2026-08-30T23:45"),  # last week
        # Planned, not happened: not work done.
        Interaction(
            user_id=alice.id, subject="Plan", kind="meeting", occurred_at=berlin("2026-09-05T10:00")
        ),
        _deal(alice, "New this week", since=berlin("2026-09-02T10:00")),
        _deal(alice, "New last month", since=berlin("2026-08-20T10:00")),
        Capture(
            user_id=alice.id,
            raw="a",
            name="a",
            status="converted",
            triaged_at=berlin("2026-09-02T10:00"),
        ),
        Capture(
            user_id=alice.id,
            raw="b",
            name="b",
            status="dismissed",
            triaged_at=berlin("2026-09-03T10:00"),
        ),
        Capture(
            user_id=alice.id,
            raw="c",
            name="c",
            status="dismissed",
            triaged_at=berlin("2026-08-03T10:00"),
        ),
        Task(user_id=alice.id, title="This week", created=berlin("2026-09-01T10:00")),
        Task(user_id=alice.id, title="Older", created=berlin("2026-07-15T10:00")),
    )

    week = (await _metrics(client, alice, "week"))["activity"]
    assert week == {
        "interactions_by_kind": [
            {"kind": "call", "count": 2},
            {"kind": "meeting", "count": 0},
            {"kind": "event", "count": 0},
            {"kind": "email", "count": 1},
            {"kind": "note", "count": 0},
            {"kind": "other", "count": 0},
        ],
        "deals_opened": 1,
        "captures_converted": 1,
        "captures_dismissed": 1,
        "tasks_created": 1,
    }

    quarter = (await _metrics(client, alice, "quarter"))["activity"]
    assert quarter["deals_opened"] == 2
    assert quarter["captures_dismissed"] == 2
    assert quarter["tasks_created"] == 2
    assert {k["kind"]: k["count"] for k in quarter["interactions_by_kind"]}["email"] == 2


# --- Trends ------------------------------------------------------------------


async def test_deals_opened_per_week_cover_ten_local_weeks_with_zeros(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(
        session_factory,
        # This week (Monday 31 August), twice — one at 00:30 local on the
        # Monday, which is still Sunday in UTC.
        _deal(alice, "Monday night", since=berlin("2026-08-31T00:30")),
        _deal(alice, "Wednesday", since=berlin("2026-09-02T10:00")),
        # Sunday 23:30 local: last week.
        _deal(alice, "Sunday late", since=berlin("2026-08-30T23:30")),
        # The oldest week in the window, and the one before it (left out).
        _deal(alice, "Oldest", since=berlin("2026-06-29T09:00")),
        _deal(alice, "Too old", since=berlin("2026-06-28T09:00")),
    )

    # The period does not matter: the series is always the last ten weeks.
    weekly = (await _metrics(client, alice, "year"))["trends"]["deals_opened_weekly"]

    assert len(weekly) == 10
    assert weekly[0] == {"start": "2026-06-29", "count": 1, "complete": True}
    assert weekly[-2] == {"start": "2026-08-24", "count": 1, "complete": True}
    assert weekly[-1] == {"start": "2026-08-31", "count": 2, "complete": False}
    assert sum(w["count"] for w in weekly) == 4
    assert [w["start"] for w in weekly][1:3] == ["2026-07-06", "2026-07-13"]


# --- Tenancy -----------------------------------------------------------------


def _everything(account: Account) -> list[Any]:
    """One of every row any metric counts, all of them inside every window."""
    deal = _deal(account, "Deal", "proposal", expected_close_date=date(2026, 9, 1))
    _event(deal, "lead", berlin("2026-09-01T09:00"))
    _event(deal, "proposal", berlin("2026-09-02T09:00"), "lead")
    won = _deal(account, "Won", "won", created_at=berlin("2026-09-01T08:00"))
    _event(won, "won", berlin("2026-09-02T09:00"))
    return [
        deal,
        won,
        _deal(account, "Open-ended", "lead", value=None, currency="USD"),
        Task(
            user_id=account.id,
            title="Slipped",
            due_date=berlin("2026-09-01T10:00"),
            created=berlin("2026-09-01T09:00"),
        ),
        Interaction(
            user_id=account.id, subject="Never confirmed", occurred_at=berlin("2026-09-01T10:00")
        ),
        Interaction(
            user_id=account.id,
            subject="Call",
            kind="call",
            done=True,
            occurred_at=berlin("2026-09-02T10:00"),
        ),
        Capture(user_id=account.id, raw="Jane", name="Jane", created_at=berlin("2026-09-01T09:00")),
        Capture(
            user_id=account.id,
            raw="Kim",
            name="Kim",
            status="converted",
            triaged_at=berlin("2026-09-02T09:00"),
        ),
    ]


async def test_another_users_rows_are_absent_from_every_total(
    session_factory: Sessions,
    client: AsyncClient,
    alice: Account,
    bob: Account,
    pinned_clock: Callable[[datetime], None],
) -> None:
    await _seed(session_factory, *_everything(alice))
    before = {p: await _metrics(client, alice, p) for p in ("week", "quarter", "year")}

    await _seed(session_factory, *_everything(bob), *_everything(bob))

    for period, body in before.items():
        assert await _metrics(client, alice, period) == body
    # And Bob's are his: twice Alice's counts, so nothing of hers leaked in.
    bob_body = await _metrics(client, bob)
    assert bob_body["attention"]["overdue_tasks"]["count"] == 2
    assert bob_body["velocity"]["sales_cycle"]["deals"] == 2
    # The fixture is worth something only if it shows up in Alice's totals.
    alice_body = before["quarter"]
    assert alice_body["pipeline"]["by_stage"]
    assert alice_body["velocity"]["entered"]
    assert alice_body["velocity"]["sales_cycle"]["deals"] == 1
    assert alice_body["attention"]["captures_waiting"]["count"] == 1
    assert alice_body["activity"]["captures_converted"] == 1
