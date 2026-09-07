"""The morning briefing: what it picks up, how it reads, and that it leaves.

Rows are written straight through the models rather than the API — this is
not an endpoint, and the interesting cases are about *when* things fall
relative to a day boundary in the operator's timezone, which is easier to
control with explicit timestamps than through the form's conventions.

The clock is pinned to 07:00 Berlin time on Friday 4 September 2026, which is
05:00 UTC — early enough that "today in Berlin" and "today in UTC" agree on
the date but not on where the day starts.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.users import User
from app.briefing import (
    MAX_LINES,
    Briefing,
    DayWindow,
    SlackDeliveryError,
    escape,
    gather_briefing,
    post_to_slack,
    render_slack,
    send_briefings,
)
from app.models.contact import Contact
from app.models.interaction import Interaction
from app.models.task import Task
from app.models.watch import Watch
from tests.conftest import Account

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 9, 4, 7, 0, tzinfo=BERLIN)  # Friday, 05:00Z
WINDOW = DayWindow.containing(NOW, BERLIN)


def berlin(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=BERLIN)


async def _seed(session_factory: async_sessionmaker[AsyncSession], *rows: Any) -> None:
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()


async def _briefing_for(
    session_factory: async_sessionmaker[AsyncSession], account: Account
) -> Briefing:
    async with session_factory() as session:
        user = await session.get(User, account.id)
        assert user is not None
        return await gather_briefing(session, user, WINDOW)


def _task(account: Account, title: str, due: datetime | None, **fields: Any) -> Task:
    """A task as the database hands one back.

    `priority` and `done` are NOT NULL with Python-side defaults, which are
    applied on flush — so an object built here and never flushed would carry
    None where a real row carries 0, and the rendering tests would be
    asserting against a state that cannot reach production.
    """
    fields.setdefault("priority", 0)
    fields.setdefault("done", False)
    return Task(user_id=account.id, title=title, due_date=due, **fields)


def _interaction(account: Account, subject: str, at: datetime, **fields: Any) -> Interaction:
    return Interaction(user_id=account.id, subject=subject, occurred_at=at, **fields)


def _watch(account: Account, name: str, due: datetime, **fields: Any) -> Watch:
    return Watch(
        user_id=account.id,
        name=name,
        url=f"https://example.com/{name}",
        recurrence_rule="weekly",
        next_due_at=due,
        **fields,
    )


# --- The day boundary --------------------------------------------------------


def test_the_window_is_the_operators_calendar_day() -> None:
    assert WINDOW.today.isoformat() == "2026-09-04"
    # Local midnight in September is 22:00Z the evening before.
    assert WINDOW.start == datetime(2026, 9, 3, 22, 0, tzinfo=UTC)
    assert WINDOW.end == datetime(2026, 9, 4, 22, 0, tzinfo=UTC)


def test_a_utc_moment_late_in_the_evening_is_already_tomorrow_locally() -> None:
    # 23:30Z on the 3rd is 01:30 Berlin on the 4th: the window is the 4th.
    window = DayWindow.containing(datetime(2026, 9, 3, 23, 30, tzinfo=UTC), BERLIN)
    assert window.today.isoformat() == "2026-09-04"


def test_days_late_counts_calendar_days_not_full_periods() -> None:
    # Filed as 23:59 yesterday, seven hours ago: one day late, not zero.
    assert WINDOW.days_late(berlin("2026-09-03T23:59")) == 1
    assert WINDOW.days_late(berlin("2026-09-01T09:00")) == 3
    assert WINDOW.days_late(berlin("2026-09-04T00:00")) == 0
    assert WINDOW.days_late(berlin("2026-09-05T00:00")) == 0


# --- What is gathered --------------------------------------------------------


async def test_tasks_split_into_overdue_and_due_today(
    session_factory: async_sessionmaker[AsyncSession], alice: Account, bob: Account
) -> None:
    await _seed(
        session_factory,
        _task(alice, "Slipped last week", berlin("2026-08-28T23:59")),
        _task(alice, "Slipped yesterday", berlin("2026-09-03T23:59")),
        # 23:59 local is 21:59Z — still today here, and the whole reason the
        # window is not computed in UTC.
        _task(alice, "Due tonight", berlin("2026-09-04T23:59")),
        _task(alice, "Due first thing", berlin("2026-09-04T00:30"), priority=2),
        _task(alice, "Due tomorrow", berlin("2026-09-05T00:30")),
        _task(alice, "No date", None),
        _task(alice, "Already done", berlin("2026-09-01T23:59"), done=True),
        _task(bob, "Bob's overdue", berlin("2026-09-01T23:59")),
    )

    briefing = await _briefing_for(session_factory, alice)

    # Most overdue first.
    assert [t.title for t in briefing.overdue_tasks] == ["Slipped last week", "Slipped yesterday"]
    # High priority first within the day.
    assert [t.title for t in briefing.tasks_today] == ["Due first thing", "Due tonight"]


async def test_planned_interactions_today_and_the_ones_never_confirmed(
    session_factory: async_sessionmaker[AsyncSession], alice: Account, bob: Account
) -> None:
    await _seed(
        session_factory,
        _interaction(alice, "Kickoff", berlin("2026-09-04T10:00"), kind="meeting"),
        _interaction(alice, "Send the deck", berlin("2026-09-04T09:00"), kind="email"),
        _interaction(alice, "Late-night call", berlin("2026-09-04T23:30"), kind="call"),
        _interaction(alice, "Already happened", berlin("2026-09-04T08:00"), done=True),
        _interaction(alice, "Next week", berlin("2026-09-07T10:00")),
        # Planned, its time passed, never ticked: the log says it happened
        # and nobody confirmed it.
        _interaction(alice, "Forgotten follow-up", berlin("2026-09-01T11:00")),
        # Logged after the fact — the form marks those done on the way in.
        _interaction(alice, "Logged note", berlin("2026-09-01T12:00"), done=True),
        _interaction(bob, "Bob's meeting", berlin("2026-09-04T10:00")),
    )

    briefing = await _briefing_for(session_factory, alice)

    assert [i.subject for i in briefing.interactions_today] == [
        "Send the deck",
        "Kickoff",
        "Late-night call",
    ]
    assert [i.subject for i in briefing.unconfirmed_interactions] == ["Forgotten follow-up"]


async def test_watches_due_today_or_overdue_and_never_a_paused_one(
    session_factory: async_sessionmaker[AsyncSession], alice: Account, bob: Account
) -> None:
    await _seed(
        session_factory,
        # Due this afternoon: belongs in this morning's briefing, not
        # tomorrow's as overdue. The API's ?due=true would not list it yet.
        _watch(alice, "karriere", berlin("2026-09-04T15:00")),
        _watch(
            alice, "ted", berlin("2026-08-30T09:00"), last_checked_at=berlin("2026-08-23T09:00")
        ),
        _watch(alice, "paused", berlin("2026-08-01T09:00"), active=False),
        _watch(alice, "next-week", berlin("2026-09-08T09:00")),
        _watch(bob, "bobs", berlin("2026-08-01T09:00")),
    )

    briefing = await _briefing_for(session_factory, alice)

    assert [w.name for w in briefing.watches_due] == ["ted", "karriere"]


async def test_a_clear_day_is_empty(
    session_factory: async_sessionmaker[AsyncSession], alice: Account
) -> None:
    await _seed(session_factory, _task(alice, "Someday", None))

    briefing = await _briefing_for(session_factory, alice)

    assert briefing.is_empty


# --- How it reads ------------------------------------------------------------


def _text_of(payload: dict[str, Any]) -> str:
    """Every mrkdwn string in the message, joined — enough to assert on."""
    parts: list[str] = []
    for block in payload["blocks"]:
        if "text" in block:
            parts.append(block["text"]["text"])
        for element in block.get("elements", []):
            parts.append(element["text"])
    return "\n".join(parts)


def _user(account: Account, name: str | None = None) -> User:
    return User(id=account.id, email=account.email, hashed_password="x", name=name)


def test_mrkdwn_control_characters_are_escaped() -> None:
    assert escape("<urgent> A & B > C") == "&lt;urgent&gt; A &amp; B &gt; C"


def test_the_message_says_who_and_what_and_how_late(alice: Account) -> None:
    contact = Contact(user_id=alice.id, name="Maria <ACME>")
    briefing = Briefing(
        user=_user(alice, name="Alice"),
        window=WINDOW,
        overdue_tasks=[
            _task(
                alice,
                "Chase the proposal",
                berlin("2026-09-01T23:59"),
                priority=2,
                contact=contact,
                recurrence_rule="weekly",
            )
        ],
        interactions_today=[
            Interaction(
                user_id=alice.id,
                subject="Kickoff",
                kind="meeting",
                occurred_at=berlin("2026-09-04T10:00"),
                duration_minutes=45,
                contacts=[contact],
            )
        ],
        watches_due=[
            Watch(
                user_id=alice.id,
                name="TED",
                url="https://ted.europa.eu/search?q=a|b",
                recurrence_rule="weekly",
                next_due_at=berlin("2026-08-30T09:00"),
                last_checked_at=berlin("2026-08-23T09:00"),
            )
        ],
    )

    payload = render_slack(briefing, app_url="https://crm.example.com")
    text = _text_of(payload)

    assert payload["blocks"][0]["text"]["text"] == "Friday, 4 September 2026"
    assert "❗ *Chase the proposal* · Maria &lt;ACME&gt; · _3 days overdue_ · repeats" in text
    # Time in the operator's zone, not the 08:00Z the database holds.
    assert "10:00 · *Kickoff* · meeting · with Maria &lt;ACME&gt; · 45 min" in text
    # A source is a link, and the one character that would cut the URL short
    # is encoded.
    assert "<https://ted.europa.eu/search?q=a%7Cb|TED> · _5 days overdue_" in text
    assert "for Alice · <https://crm.example.com|Open tinyCRM>" in text
    # The notification preview carries the counts on its own.
    assert payload["text"] == "Fri 4 Sep: 1 overdue · 1 on the calendar · 1 to sweep"


def test_a_clear_day_still_produces_a_message(alice: Account) -> None:
    payload = render_slack(Briefing(user=_user(alice), window=WINDOW))

    assert "Clear day" in _text_of(payload)
    assert "for alice@example.com" in _text_of(payload)
    assert payload["text"] == "Fri 4 Sep: nothing due"


def test_a_long_section_is_capped_with_a_count_of_the_rest(alice: Account) -> None:
    briefing = Briefing(
        user=_user(alice),
        window=WINDOW,
        overdue_tasks=[
            _task(alice, f"Task {n:02d}", berlin("2026-09-01T23:59")) for n in range(MAX_LINES + 5)
        ],
    )

    text = _text_of(render_slack(briefing))

    assert f"*Overdue* ({MAX_LINES + 5})" in text
    assert f"Task {MAX_LINES - 1:02d}" in text
    assert f"Task {MAX_LINES:02d}" not in text
    assert "…and 5 more" in text


def test_a_never_swept_source_says_so_rather_than_counting_days(alice: Account) -> None:
    briefing = Briefing(
        user=_user(alice),
        window=WINDOW,
        watches_due=[
            Watch(
                user_id=alice.id,
                name="Fresh",
                url="https://example.com/fresh",
                recurrence_rule="weekly",
                next_due_at=berlin("2026-08-01T09:00"),
            ),
            Watch(
                user_id=alice.id,
                name="Later today",
                url="https://example.com/later",
                recurrence_rule="weekly",
                next_due_at=berlin("2026-09-04T15:00"),
                last_checked_at=berlin("2026-08-28T15:00"),
            ),
        ],
    )

    text = _text_of(render_slack(briefing))

    assert "Fresh> · never swept" in text
    assert "Later today> · due today" in text


# --- Delivery ----------------------------------------------------------------


class _Posted:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, webhook_url: str, payload: dict[str, Any]) -> None:
        self.calls.append((webhook_url, payload))


async def test_one_message_per_active_user_and_none_for_a_deactivated_one(
    session_factory: async_sessionmaker[AsyncSession], alice: Account, bob: Account
) -> None:
    await _seed(
        session_factory,
        User(
            id=uuid.uuid4(),
            email="carol@example.com",
            hashed_password="x",
            is_active=False,
            is_verified=True,
        ),
        _task(alice, "Alice's task", berlin("2026-09-04T23:59")),
        _task(bob, "Bob's task", berlin("2026-09-01T23:59")),
    )
    posted = _Posted()

    briefings = await send_briefings(
        session_factory,
        webhook_url="https://hooks.slack.test/abc",
        tz=BERLIN,
        now=NOW,
        post=posted,
    )

    assert [b.user.email for b in briefings] == ["alice@example.com", "bob@example.com"]
    assert [url for url, _ in posted.calls] == ["https://hooks.slack.test/abc"] * 2
    assert posted.calls[0][1]["text"] == "Fri 4 Sep: 1 due today"
    assert posted.calls[1][1]["text"] == "Fri 4 Sep: 1 overdue"


async def test_a_refused_delivery_ends_the_run(
    session_factory: async_sessionmaker[AsyncSession], alice: Account, bob: Account
) -> None:
    def refuse(webhook_url: str, payload: dict[str, Any]) -> None:
        raise SlackDeliveryError("Slack refused the message: HTTP 404 no_service")

    with pytest.raises(SlackDeliveryError, match="no_service"):
        await send_briefings(
            session_factory,
            webhook_url="https://hooks.slack.test/abc",
            tz=BERLIN,
            now=NOW,
            post=refuse,
        )


class _Response(io.BytesIO):
    """Just enough of an HTTPResponse to be used as a context manager."""

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_slack_saying_ok_is_a_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        seen.append(request)
        return _Response(b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    post_to_slack("https://hooks.slack.test/abc", {"text": "hi", "blocks": []})

    (request,) = seen
    assert request.full_url == "https://hooks.slack.test/abc"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.data == b'{"text": "hi", "blocks": []}'


def test_a_4xx_from_slack_is_reported_with_its_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "Not Found",
            # HTTPError wants real response headers here; nothing under test
            # reads them, and building a Message just to satisfy the signature
            # would say less about the case than this does.
            None,  # type: ignore[arg-type]
            io.BytesIO(b"no_service"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SlackDeliveryError, match="HTTP 404 no_service"):
        post_to_slack("https://hooks.slack.test/abc", {"text": "hi", "blocks": []})


def test_a_200_that_is_not_ok_is_not_a_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    # A captive portal or a misrouted proxy answers 200 with HTML.
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout: _Response(b"<html>login</html>")
    )

    with pytest.raises(SlackDeliveryError, match="unexpected reply"):
        post_to_slack("https://hooks.slack.test/abc", {"text": "hi", "blocks": []})


def test_an_unreachable_slack_is_reported_without_the_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SlackDeliveryError) as excinfo:
        post_to_slack("https://hooks.slack.test/secret-token", {"text": "hi", "blocks": []})

    # The URL is a credential; the error goes to the job log.
    assert "secret-token" not in str(excinfo.value)
    assert "Name or service not known" in str(excinfo.value)


def test_the_window_survives_a_dst_switch() -> None:
    # 25 October 2026: clocks go back in Berlin, the day is 25 hours long.
    # Compared as instants — subtracting two datetimes that share a tzinfo
    # ignores the offsets, which is exactly the trap the window avoids.
    window = DayWindow.containing(datetime(2026, 10, 25, 7, 0, tzinfo=BERLIN), BERLIN)
    assert window.end.astimezone(UTC) - window.start.astimezone(UTC) == timedelta(hours=25)
