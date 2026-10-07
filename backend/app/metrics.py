"""The dashboard's numbers (#138, DASHBOARD.md): one grouped query per metric.

Everything here aggregates in SQL — no metric loads rows into Python to count
them. Each function takes the user's id and returns plain response models, so
the router only resolves the period and assembles the groups.

The rules from DASHBOARD.md that shape every function:

1. *Open-ended deals are not zero.* A money figure is always a pair: the sum of
   the amounts that can be derived, and how many deals have none
   (`expected_value IS NULL`).
2. *Currencies are never added.* Every money aggregate groups by currency.
3. *Decimal all the way.* Sums come back as `Decimal` and serialise as strings.
4. *"This week" is local.* Periods are built from the briefing's `DayWindow`.

Plus `user_id` on every query. There is one operator, so a missing filter
would never be noticed in use; tests/test_metrics.py proves it with a second
user's rows.

A draft is not in play (#255): the pipeline, its velocity and what needs
attention all start counting at `lead`, when the letter has gone out. Only the
activity group counts a draft, because preparing one is work done.

And nothing archived is counted, in any number (#140). Every figure links to
the list behind it, and no list shows an archived row; a won deal that was
archived leaves the conversion rate until it is restored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal, get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import (
    ColumnElement,
    Date,
    Integer,
    and_,
    case,
    cast,
    distinct,
    func,
    literal,
    select,
    type_coerce,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import live
from app.briefing import DayWindow, briefing_queries
from app.db import count_rows
from app.models import Capture, Deal, DealStageEvent, Interaction, Task
from app.models.deal import IN_PLAY_STAGES, OPEN_STAGES, WON_STAGES, overdue_on
from app.schemas.interaction import InteractionKind
from app.schemas.metrics import (
    ActivityMetrics,
    AttentionMetrics,
    AttentionRow,
    InteractionKindCount,
    ListQuery,
    MoneyByCurrency,
    OldestDeal,
    PipelineMetrics,
    SalesCycle,
    StageConversion,
    StageEntered,
    StageMoney,
    StageVelocity,
    TrendMetrics,
    VelocityMetrics,
    WeekCount,
)

PeriodKind = Literal["week", "month", "quarter", "year"]

# The order deals move through when things go well. `lost` is not on it: a
# deal that went from proposal to lost did not advance.
PIPELINE = OPEN_STAGES + WON_STAGES

# Committed but not delivered: agreed, and the work not finished.
COMMITTED_STAGES = ("won", "running")

CENT = Decimal("0.01")


def _first_of_month(day: date, months_ahead: int = 0) -> date:
    index = day.year * 12 + (day.month - 1) + months_ahead
    return date(index // 12, index % 12 + 1, 1)


@dataclass(frozen=True)
class Period:
    """A calendar week, month, quarter or year in the operator's timezone.

    The one containing today, half-open like `DayWindow`: `start` is local
    midnight on the first day, `end` local midnight on the first day after.
    Both come from `DayWindow`, so a period starts exactly where the briefing
    says that day starts — across a DST switch included.
    """

    kind: PeriodKind
    first: date
    # The first day *after* the period; `end` is its local midnight.
    after: date
    start: datetime
    end: datetime
    # Today, for the "now" metrics that sit beside the period ones.
    day: DayWindow

    @classmethod
    def containing(cls, kind: PeriodKind, now: datetime, tz: ZoneInfo) -> Period:
        day = DayWindow.containing(now, tz)
        today = day.today
        if kind == "week":
            # ISO weeks: Monday first, as a European calendar has it.
            first = today - timedelta(days=today.weekday())
            after = first + timedelta(days=7)
        elif kind == "month":
            first = _first_of_month(today)
            after = _first_of_month(today, 1)
        elif kind == "quarter":
            first = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
            after = _first_of_month(first, 3)
        else:
            first = date(today.year, 1, 1)
            after = date(today.year + 1, 1, 1)
        return cls(
            kind=kind,
            first=first,
            after=after,
            start=_day(first, tz).start,
            end=_day(after, tz).start,
            day=day,
        )

    @property
    def tz(self) -> ZoneInfo:
        return self.day.tz

    def contains(self, column: Any) -> ColumnElement[bool]:
        return and_(column >= self.start, column < self.end)


def _day(on: date, tz: ZoneInfo) -> DayWindow:
    # Noon is inside the day on every calendar, DST switches included, so the
    # window built around it is that day's.
    return DayWindow.containing(datetime.combine(on, time(12), tzinfo=tz), tz)


def _local_date(column: Any, tz: ZoneInfo) -> ColumnElement[date]:
    """The calendar day `column` falls on in `tz` — what `DayWindow.days_late`
    compares, done in SQL."""
    return cast(func.timezone(tz.key, column), Date)


def _days_since(column: Any, day: DayWindow) -> ColumnElement[int]:
    """Whole calendar days from `column` to today, as `DayWindow.days_late`."""
    # date - date is an integer in Postgres; SQLAlchemy types it as a date.
    return type_coerce(literal(day.today, Date) - _local_date(column, day.tz), Integer)


def _money(value: Decimal | None) -> Decimal:
    # SUM over nothing but open-ended deals is NULL; the pair then reads
    # "0.00, n open-ended", which is the honest version of that.
    return (value or Decimal(0)).quantize(CENT)


def _median(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _stage_rank(column: Any) -> ColumnElement[int]:
    """Position in PIPELINE; NULL for `lost`, so it never counts as ahead."""
    return case({stage: i for i, stage in enumerate(PIPELINE)}, value=column)


# --- A · What is in play -----------------------------------------------------


async def pipeline_metrics(session: AsyncSession, user_id: UUID) -> PipelineMetrics:
    def money_query(*group: Any) -> Any:
        return (
            select(
                *group,
                Deal.currency,
                func.count(),
                func.sum(Deal.expected_value),
                func.count().filter(Deal.expected_value.is_(None)),
            )
            .where(Deal.user_id == user_id, live(Deal))
            .group_by(*group, Deal.currency)
        )

    by_stage = await session.execute(money_query(Deal.stage).where(Deal.stage.in_(IN_PLAY_STAGES)))
    committed = await session.execute(money_query().where(Deal.stage.in_(COMMITTED_STAGES)))

    stages = [
        StageMoney(stage=stage, currency=currency, count=n, value=_money(total), open_ended=oe)
        for stage, currency, n, total, oe in by_stage
    ]
    stages.sort(key=lambda s: (IN_PLAY_STAGES.index(s.stage), s.currency))
    return PipelineMetrics(
        by_stage=stages,
        committed=sorted(
            (
                MoneyByCurrency(currency=currency, count=n, value=_money(total), open_ended=oe)
                for currency, n, total, oe in committed
            ),
            key=lambda m: m.currency,
        ),
    )


# --- B · Is it moving --------------------------------------------------------


async def velocity_metrics(session: AsyncSession, user_id: UUID, period: Period) -> VelocityMetrics:
    day = period.day
    open_deals = Deal.user_id == user_id, Deal.stage.in_(IN_PLAY_STAGES), live(Deal)

    in_stage = _days_since(Deal.stage_changed_at, day)
    medians = await session.execute(
        select(
            Deal.stage,
            func.count(),
            func.percentile_cont(0.5).within_group(in_stage),
        )
        .where(*open_deals)
        .group_by(Deal.stage)
    )
    # One row per stage: the deal that has sat in it longest.
    oldest = await session.execute(
        select(Deal.stage, Deal.id, Deal.title, Deal.stage_changed_at, in_stage)
        .where(*open_deals)
        .distinct(Deal.stage)
        .order_by(Deal.stage, Deal.stage_changed_at.asc(), Deal.id.asc())
    )
    oldest_by_stage = {
        stage: OldestDeal(id=id_, title=title, stage_changed_at=at, days_in_stage=days)
        for stage, id_, title, at, days in oldest
    }
    by_stage = [
        StageVelocity(
            stage=stage,
            count=n,
            median_days_in_stage=_median(median),
            oldest=oldest_by_stage[stage],
        )
        for stage, n, median in medians
    ]
    by_stage.sort(key=lambda s: IN_PLAY_STAGES.index(s.stage))

    # Distinct deals, not events: a deal moved back into proposal and forward
    # again entered proposal once as far as throughput is concerned.
    entered = await session.execute(
        select(DealStageEvent.to_stage, func.count(distinct(DealStageEvent.deal_id)))
        .join(Deal, Deal.id == DealStageEvent.deal_id)
        .where(Deal.user_id == user_id, live(Deal), period.contains(DealStageEvent.changed_at))
        .group_by(DealStageEvent.to_stage)
    )
    entered_rows = [StageEntered(stage=stage, count=n) for stage, n in entered]
    stage_order = (*PIPELINE, "lost")
    entered_rows.sort(key=lambda s: stage_order.index(s.stage))

    return VelocityMetrics(
        by_stage=by_stage,
        entered=entered_rows,
        conversion=await _conversion(session, user_id),
        sales_cycle=await _sales_cycle(session, user_id, period),
    )


async def _conversion(session: AsyncSession, user_id: UUID) -> list[StageConversion]:
    """Of the deals that ever entered each stage in play, how many went further.

    "Further" is any later stage on PIPELINE entered after it, so a deal that
    skipped from qualified straight to negotiation still advanced out of
    qualified. Moving to `lost` is not advancing.

    All-time rather than per period: a deal that entered proposal last week has
    not had the chance to move on, and a weekly rate would mostly measure that.
    It does count from when the stage log started (#115) — deals older than
    the log enter it at their first move.
    """
    firsts = (
        select(
            DealStageEvent.deal_id.label("deal_id"),
            DealStageEvent.to_stage.label("stage"),
            func.min(DealStageEvent.changed_at).label("at"),
        )
        .join(Deal, Deal.id == DealStageEvent.deal_id)
        .where(Deal.user_id == user_id, live(Deal))
        .group_by(DealStageEvent.deal_id, DealStageEvent.to_stage)
        .subquery()
    )
    entry = firsts.alias("entry")
    later = firsts.alias("later")
    rows = await session.execute(
        select(
            entry.c.stage,
            func.count(distinct(entry.c.deal_id)),
            func.count(distinct(later.c.deal_id)),
        )
        .select_from(entry)
        .outerjoin(
            later,
            and_(
                later.c.deal_id == entry.c.deal_id,
                _stage_rank(later.c.stage) > _stage_rank(entry.c.stage),
                later.c.at > entry.c.at,
            ),
        )
        .where(entry.c.stage.in_(IN_PLAY_STAGES))
        .group_by(entry.c.stage)
    )
    found = {stage: (n, advanced) for stage, n, advanced in rows}
    return [
        StageConversion(
            stage=stage,
            entered=found.get(stage, (0, 0))[0],
            advanced=found.get(stage, (0, 0))[1],
        )
        for stage in IN_PLAY_STAGES
    ]


async def _sales_cycle(session: AsyncSession, user_id: UUID, period: Period) -> SalesCycle:
    """Calendar days from opening a deal to first winning it, for the deals
    first won in this period.

    Opened is `Deal.created_at`, not the first logged event: deals older than
    the stage log have no creation event, and counting from their first move
    would make every one of them look fast.
    """
    won_at = func.min(DealStageEvent.changed_at).filter(DealStageEvent.to_stage.in_(WON_STAGES))
    per_deal = (
        select(Deal.created_at.label("opened"), won_at.label("won"))
        .join(DealStageEvent, DealStageEvent.deal_id == Deal.id)
        .where(Deal.user_id == user_id, live(Deal))
        .group_by(Deal.id, Deal.created_at)
        .subquery()
    )
    days = _local_date(per_deal.c.won, period.tz) - _local_date(per_deal.c.opened, period.tz)
    n, median = (
        await session.execute(
            select(func.count(), func.percentile_cont(0.5).within_group(days)).where(
                period.contains(per_deal.c.won)
            )
        )
    ).one()
    return SalesCycle(deals=n, median_days=_median(median))


# --- D · What is rotting -----------------------------------------------------


async def attention_metrics(
    session: AsyncSession, user_id: UUID, period: Period
) -> AttentionMetrics:
    """Counts of what needs attention today, each with the list behind it.

    The briefing's own queries (`briefing_queries`), counted: the dashboard and
    the 07:00 message must never disagree about what is late.
    """
    day = period.day
    briefing = briefing_queries(user_id, day)

    overdue_deals = select(Deal).where(Deal.user_id == user_id, overdue_on(day.today), live(Deal))
    oldest_capture = await session.scalar(
        briefing.captures_waiting.with_only_columns(func.min(Capture.created_at)).order_by(None)
    )

    return AttentionMetrics(
        stalled_deals=AttentionRow(
            count=await count_rows(session, briefing.stalled_deals),
            list=ListQuery(path="/deals/", params={"stalled": "true"}),
        ),
        overdue_deals=AttentionRow(
            count=await count_rows(session, overdue_deals),
            list=ListQuery(path="/deals/", params={"overdue": "true"}),
        ),
        overdue_tasks=AttentionRow(
            count=await count_rows(session, briefing.overdue_tasks),
            list=ListQuery(path="/briefing/", field="overdue_tasks"),
        ),
        unconfirmed_interactions=AttentionRow(
            count=await count_rows(session, briefing.unconfirmed_interactions),
            list=ListQuery(path="/briefing/", field="unconfirmed_interactions"),
        ),
        captures_waiting=AttentionRow(
            count=await count_rows(session, briefing.captures_waiting),
            list=ListQuery(path="/captures/", params={"status": "new"}),
            oldest_days=None if oldest_capture is None else day.days_late(oldest_capture),
        ),
    )


# --- E · Am I doing the work -------------------------------------------------


async def activity_metrics(session: AsyncSession, user_id: UUID, period: Period) -> ActivityMetrics:
    # Logged means it happened: a planned call next week is not work done yet,
    # and one planned and never confirmed is the briefing's problem, not this.
    kind_rows = await session.execute(
        select(Interaction.kind, func.count())
        .where(
            Interaction.user_id == user_id,
            Interaction.done.is_(True),
            period.contains(Interaction.occurred_at),
            live(Interaction),
        )
        .group_by(Interaction.kind)
    )
    kinds: dict[str, int] = {kind: n for kind, n in kind_rows}
    deals_opened = await session.scalar(
        select(func.count()).where(
            Deal.user_id == user_id, period.contains(Deal.created_at), live(Deal)
        )
    )
    triaged_rows = await session.execute(
        select(Capture.status, func.count())
        .where(Capture.user_id == user_id, period.contains(Capture.triaged_at), live(Capture))
        .group_by(Capture.status)
    )
    triaged: dict[str, int] = {status: n for status, n in triaged_rows}
    tasks_created = await session.scalar(
        select(func.count()).where(
            Task.user_id == user_id, period.contains(Task.created), live(Task)
        )
    )
    return ActivityMetrics(
        # Every kind, zeros included, so the shape does not change with the data.
        interactions_by_kind=[
            InteractionKindCount(kind=kind, count=kinds.get(kind, 0))
            for kind in get_args(InteractionKind)
        ],
        deals_opened=deals_opened or 0,
        captures_converted=triaged.get("converted", 0),
        captures_dismissed=triaged.get("dismissed", 0),
        tasks_created=tasks_created or 0,
    )


# --- Trends -------------------------------------------------------------------

# How many calendar weeks a weekly series covers: enough to tell a slow week
# from a slowing trend, few enough to read at a glance.
WEEKS = 10


async def trend_metrics(
    session: AsyncSession, user_id: UUID, now: datetime, tz: ZoneInfo
) -> TrendMetrics:
    """Deals opened per ISO week, the last WEEKS weeks in the operator's
    timezone. The week boundaries are Period's, so "this week" here is the
    same week the dashboard's `period=week` reports."""
    this_week = Period.containing("week", now, tz)
    weeks = [this_week.first - timedelta(weeks=n) for n in range(WEEKS - 1, -1, -1)]
    since = _day(weeks[0], tz).start
    # date_trunc('week') is ISO: Monday. Truncated in local time, so a deal
    # opened at 00:30 on a Monday in Berlin is that week's, not the last.
    week_of = cast(func.date_trunc("week", func.timezone(tz.key, Deal.created_at)), Date)
    rows = await session.execute(
        select(week_of, func.count())
        .where(
            Deal.user_id == user_id,
            live(Deal),
            Deal.created_at >= since,
            Deal.created_at < this_week.end,
        )
        .group_by(week_of)
    )
    counts: dict[date, int] = {start: n for start, n in rows}
    return TrendMetrics(
        deals_opened_weekly=[
            WeekCount(start=start, count=counts.get(start, 0), complete=start != this_week.first)
            for start in weeks
        ]
    )
