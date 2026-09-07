"""The morning briefing: what is due today, what slipped, what to sweep.

Everything the dashboard's "Upcoming" panel knows is only visible while a tab
is open, which makes it passive. This is the same information, pushed: one
Slack message per user on weekday mornings, sent by `scripts/send_briefing.py`
from a Kubernetes CronJob (charts/tinycrm/templates/briefing-cronjob.yaml).

Deliberately no in-process scheduler. A loop inside the API would fire once
per replica or need a lock; a CronJob fires once, shows up in `kubectl get
jobs`, and fails visibly when delivery does. Slack rather than mail for the
same reason T23 has not shipped yet: an incoming webhook is one URL and one
POST, and there is no mail sender to build first.

"Today" is a calendar day in the operator's timezone (BRIEFING_TIMEZONE), not
UTC. The task form files a due date as 23:59 local, which is 21:59Z in summer
— a UTC window would still call that today, but a task filed at 00:30 local
would slip a day, and a meeting at 23:30 local would land in tomorrow's
briefing. All comparisons happen on aware timestamps against a window
computed once per run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.users import User

# The package, not the three modules this file names: a mapper is configured
# against the whole registry, so importing only Task/Interaction/Watch leaves
# `Interaction.projects` unable to resolve "Project" and the first query
# fails. See app/models/__init__.py — the API is only safe here because it
# imports every router.
from app.models import Interaction, Task, Watch

logger = logging.getLogger(__name__)

# Lines per section before "…and n more". Slack caps a section block at 3000
# characters, and a briefing that scrolls is one nobody reads anyway.
MAX_LINES = 15

# How long to wait for Slack before giving up. The CronJob retries the whole
# run, so this only has to be long enough for a slow response, not an outage.
SLACK_TIMEOUT_SECONDS = 15

# Called with the webhook URL and the message payload; must raise on failure.
# Injected so a dry run can print instead, and so tests never touch the network.
Poster = Callable[[str, dict[str, Any]], None]


class SlackDeliveryError(RuntimeError):
    """Slack did not accept the message. The text never carries the webhook
    URL — it is a bearer credential, and this ends up in the job's log."""


@dataclass(frozen=True)
class DayWindow:
    """One calendar day in the operator's timezone, as aware bounds.

    `start` is local midnight, `end` the next one. Half-open, so 23:59 local
    is today and 00:00 tomorrow is not. The bounds carry their own offset, so
    comparing them against a timestamptz column is an instant comparison —
    the database never sees a naive value.
    """

    today: date
    start: datetime
    end: datetime
    tz: ZoneInfo

    @classmethod
    def containing(cls, now: datetime, tz: ZoneInfo) -> DayWindow:
        today = now.astimezone(tz).date()
        # combine() with a ZoneInfo resolves the offset per wall-clock time,
        # so a window that spans a DST switch is 23 or 25 hours long, as it
        # should be, rather than a fixed 24.
        start = datetime.combine(today, time.min, tzinfo=tz)
        end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
        return cls(today=today, start=start, end=end, tz=tz)

    def local(self, moment: datetime) -> datetime:
        return moment.astimezone(self.tz)

    def days_late(self, moment: datetime) -> int:
        """Whole calendar days before today; 0 when it is today or later.

        Calendar days, not 24-hour periods: something due yesterday at 23:59
        is one day late at 07:00 this morning, not zero.
        """
        return max(0, (self.today - self.local(moment).date()).days)


@dataclass
class Briefing:
    """One user's day, in the order it is worked."""

    user: User
    window: DayWindow
    # Open, due before today. Most overdue first.
    overdue_tasks: list[Task] = field(default_factory=list)
    # Open, due today. High priority first.
    tasks_today: list[Task] = field(default_factory=list)
    # Planned for today and not yet marked as happened — any kind, because a
    # planned email is a commitment too.
    interactions_today: list[Interaction] = field(default_factory=list)
    # Planned before today and never confirmed. The form marks anything logged
    # in the past as done, so these are the ones that were scheduled and then
    # neither happened nor got cancelled — the log is lying until they are.
    unconfirmed_interactions: list[Interaction] = field(default_factory=list)
    # Active sources due today or overdue. "Due today" rather than "due now"
    # (the API's `?due=true`): a source due at 15:00 belongs in the 07:00
    # briefing, not in tomorrow's as overdue.
    watches_due: list[Watch] = field(default_factory=list)

    @property
    def recipient(self) -> str:
        return self.user.name or self.user.email

    @property
    def is_empty(self) -> bool:
        return not (
            self.overdue_tasks
            or self.tasks_today
            or self.interactions_today
            or self.unconfirmed_interactions
            or self.watches_due
        )


async def gather_briefing(session: AsyncSession, user: User, window: DayWindow) -> Briefing:
    """Everything that wants `user`'s attention today."""
    open_tasks = select(Task).where(Task.user_id == user.id, Task.done.is_(False))
    overdue_tasks = await session.scalars(
        open_tasks.where(Task.due_date < window.start).order_by(
            Task.due_date.asc(), Task.priority.desc(), Task.id.asc()
        )
    )
    tasks_today = await session.scalars(
        open_tasks.where(Task.due_date >= window.start, Task.due_date < window.end).order_by(
            Task.priority.desc(), Task.due_date.asc(), Task.id.asc()
        )
    )

    planned = select(Interaction).where(Interaction.user_id == user.id, Interaction.done.is_(False))
    interactions_today = await session.scalars(
        planned.where(
            Interaction.occurred_at >= window.start, Interaction.occurred_at < window.end
        ).order_by(Interaction.occurred_at.asc(), Interaction.id.asc())
    )
    unconfirmed = await session.scalars(
        planned.where(Interaction.occurred_at < window.start).order_by(
            Interaction.occurred_at.asc(), Interaction.id.asc()
        )
    )

    watches_due = await session.scalars(
        select(Watch)
        .where(Watch.user_id == user.id, Watch.active.is_(True), Watch.next_due_at < window.end)
        .order_by(Watch.next_due_at.asc(), Watch.id.asc())
    )

    return Briefing(
        user=user,
        window=window,
        overdue_tasks=list(overdue_tasks),
        tasks_today=list(tasks_today),
        interactions_today=list(interactions_today),
        unconfirmed_interactions=list(unconfirmed),
        watches_due=list(watches_due),
    )


# --- Rendering ---------------------------------------------------------------


def escape(text: str) -> str:
    """Slack's mrkdwn reads &, < and > as control characters — a task called
    "<urgent> A & B" would otherwise render as a broken link."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _link(url: str, label: str) -> str:
    # The two characters that would end the URL part of <url|label> early.
    safe_url = url.replace("|", "%7C").replace(">", "%3E")
    return f"<{safe_url}|{escape(label)}>"


def _late(days: int) -> str:
    return "_1 day overdue_" if days == 1 else f"_{days} days overdue_"


def _task_line(task: Task, window: DayWindow) -> str:
    parts = [f"*{escape(task.title)}*"]
    about = " · ".join(escape(p) for p in (task.contact_name, task.deal_title) if p)
    if about:
        parts.append(about)
    if task.due_date is not None and (late := window.days_late(task.due_date)):
        parts.append(_late(late))
    if task.recurrence_rule is not None:
        parts.append("repeats")
    # Red is the overdue colour in the app (T41); here the mark is a symbol so
    # an overdue low-priority task still reads differently from an urgent one.
    prefix = "❗ " if task.priority >= 2 else ""
    return f"• {prefix}{' · '.join(parts)}"


def _interaction_line(interaction: Interaction, window: DayWindow, *, with_date: bool) -> str:
    local = window.local(interaction.occurred_at)
    when = f"{local:%a} {local.day} {local:%b}" if with_date else f"{local:%H:%M}"
    parts = [when, f"*{escape(interaction.subject)}*", interaction.kind]
    who = [c.name for c in interaction.contacts] or [o.name for o in interaction.organizations]
    if who:
        parts.append("with " + ", ".join(escape(name) for name in who))
    if interaction.duration_minutes:
        parts.append(f"{interaction.duration_minutes} min")
    return "• " + " · ".join(parts)


def _watch_line(watch: Watch, window: DayWindow) -> str:
    parts = [_link(watch.url, watch.name)]
    if watch.organization_name:
        parts.append(escape(watch.organization_name))
    if watch.last_checked_at is None:
        parts.append("never swept")
    elif late := window.days_late(watch.next_due_at):
        parts.append(_late(late))
    else:
        parts.append("due today")
    return "• " + " · ".join(parts)


def _capped(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_LINES:
        return lines
    hidden = len(lines) - MAX_LINES
    return [*lines[:MAX_LINES], f"…and {hidden} more"]


def _section(title: str, lines: list[str]) -> dict[str, Any]:
    body = "\n".join(_capped(lines))
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{title}* ({len(lines)})\n{body}"},
    }


def _count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def render_slack(briefing: Briefing, *, app_url: str | None = None) -> dict[str, Any]:
    """The message as a Slack incoming-webhook payload.

    `text` is the notification preview and the fallback for clients that do
    not render blocks, so it has to say the numbers on its own.
    """
    window = briefing.window
    heading = f"{window.today:%A}, {window.today.day} {window.today:%B %Y}"

    sections = [
        ("Overdue", [_task_line(t, window) for t in briefing.overdue_tasks]),
        ("Due today", [_task_line(t, window) for t in briefing.tasks_today]),
        (
            "On the calendar today",
            [_interaction_line(i, window, with_date=False) for i in briefing.interactions_today],
        ),
        (
            "Planned, never confirmed",
            [
                _interaction_line(i, window, with_date=True)
                for i in briefing.unconfirmed_interactions
            ],
        ),
        ("Sources to sweep", [_watch_line(w, window) for w in briefing.watches_due]),
    ]

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": heading}},
    ]
    if briefing.is_empty:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Nothing due, nothing overdue, nothing to sweep. Clear day.",
                },
            }
        )
    else:
        blocks.extend(_section(title, lines) for title, lines in sections if lines)

    footer = [f"for {escape(briefing.recipient)}"]
    if app_url:
        footer.append(_link(app_url, "Open tinyCRM"))
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " · ".join(footer)}],
        }
    )

    if briefing.is_empty:
        summary = "nothing due"
    else:
        counts = [
            (len(briefing.overdue_tasks), "overdue"),
            (len(briefing.tasks_today), "due today"),
            (len(briefing.interactions_today), "on the calendar"),
            (len(briefing.unconfirmed_interactions), "unconfirmed"),
            (len(briefing.watches_due), "to sweep"),
        ]
        summary = " · ".join(f"{n} {label}" for n, label in counts if n)
    text = f"{window.today:%a} {window.today.day} {window.today:%b}: {summary}"

    return {"text": text, "blocks": blocks}


# --- Delivery ----------------------------------------------------------------


def post_to_slack(webhook_url: str, payload: dict[str, Any]) -> None:
    """POST one message to an incoming webhook.

    Slack answers a bare "ok" on success and a short error code with a 4xx
    otherwise. Anything else is a failure, including a 200 that does not say
    "ok" — a captive portal or a misconfigured proxy would produce exactly
    that, and the run must not report a delivery that never happened.
    """
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=SLACK_TIMEOUT_SECONDS) as response:
            reply = response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()
        raise SlackDeliveryError(f"Slack refused the message: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise SlackDeliveryError(f"could not reach Slack: {exc.reason}") from exc
    if reply.strip() != "ok":
        raise SlackDeliveryError(f"unexpected reply from Slack: {reply!r}")


async def send_briefings(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    webhook_url: str,
    tz: ZoneInfo,
    now: datetime | None = None,
    app_url: str | None = None,
    post: Poster = post_to_slack,
) -> list[Briefing]:
    """Gather and deliver one briefing per active user.

    One webhook, one channel: every user's briefing lands in the same place.
    That is the single-operator shape this app is built for (PLAN.md, out of
    scope: teams); a second real user needs a destination per user first.

    The first delivery failure raises and ends the run — with one webhook, a
    refusal for one user is a refusal for all, and the CronJob retries the
    whole thing.
    """
    window = DayWindow.containing(now or datetime.now(UTC), tz)
    briefings: list[Briefing] = []
    async with session_factory() as session:
        # Filtered here rather than in SQL: fastapi-users types `is_active` as
        # a plain bool under TYPE_CHECKING, and there is one operator's worth
        # of rows in this table.
        users = await session.scalars(select(User).order_by(User.email))
        for user in users:
            if not user.is_active:
                continue
            briefing = await gather_briefing(session, user, window)
            payload = render_slack(briefing, app_url=app_url)
            # urllib blocks; keep the event loop free rather than stalling
            # the session's connection for the duration of the request.
            await asyncio.to_thread(post, webhook_url, payload)
            # Not "delivered": `post` is injected, and a dry run reaches here
            # having printed rather than sent.
            logger.info("Briefing for %s: %s", user.email, payload["text"])
            briefings.append(briefing)
    return briefings
