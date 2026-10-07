"""GET /metrics/dashboard — the dashboard's numbers, one model per group.

The groups follow DASHBOARD.md. A group that cannot be computed yet is not a
field here at all, rather than an empty one: an empty `outcomes` would read as
"nothing came off", which is a different and much worse claim than "not
measured". `outcomes` (C) and `delivery` (F) arrive with the work they need.

Money is `Decimal` and serialises as a string, as on `DealRead`. Every money
figure carries `open_ended`, the deals with no derivable amount, beside it.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.deal import DealStage
from app.schemas.interaction import InteractionKind


class PeriodRead(BaseModel):
    """The window the period figures cover, resolved: the client asked for
    "quarter", this says which one and in which timezone."""

    kind: str
    # First day of the period.
    start: date
    # First day *after* it — half-open, like every window in the app.
    end: date
    timezone: str
    # The day the "now" figures are for.
    today: date


# --- A · What is in play -----------------------------------------------------


class MoneyByCurrency(BaseModel):
    currency: str
    count: int
    # Sum of the amounts that can be derived. Never includes `open_ended`.
    value: Decimal
    # Deals with no derivable amount (`expected_value` is null): priced by rate
    # with no volume estimate, or not priced yet. Counted, never summed as 0.
    open_ended: int


class StageMoney(MoneyByCurrency):
    stage: DealStage


class PipelineMetrics(BaseModel):
    """Now. Weighted pipeline is left out until stage-default probabilities
    exist (#120); today it would be a sum over an arbitrary subset."""

    # Open stages, pipeline order, one row per stage and currency. A stage
    # with no deals has no row.
    by_stage: list[StageMoney]
    # Won and running: agreed and not yet delivered. One row per currency.
    committed: list[MoneyByCurrency]


# --- B · Is it moving --------------------------------------------------------


class OldestDeal(BaseModel):
    id: UUID
    title: str
    stage_changed_at: datetime
    days_in_stage: int


class StageVelocity(BaseModel):
    """Now, one open stage."""

    stage: DealStage
    # Open deals currently in the stage.
    count: int
    # Calendar days since each entered the stage, in the operator's timezone.
    # A median, not a mean: one deal parked for a year would drag a mean.
    median_days_in_stage: float | None
    oldest: OldestDeal


class StageEntered(BaseModel):
    """In the period: distinct deals that entered `stage`."""

    stage: DealStage
    count: int


class StageConversion(BaseModel):
    """All-time: of the deals that ever entered `stage`, how many later
    entered a stage further along the pipeline (lost does not count)."""

    stage: DealStage
    entered: int
    advanced: int


class SalesCycle(BaseModel):
    """Deals first won in the period, and the median calendar days from
    opening each to winning it. Null median when none were won."""

    deals: int
    median_days: float | None


class VelocityMetrics(BaseModel):
    # Open stages that hold a deal, pipeline order.
    by_stage: list[StageVelocity]
    # Stages entered in the period; a stage nobody entered has no row.
    entered: list[StageEntered]
    # Every open stage, pipeline order, zeros included.
    conversion: list[StageConversion]
    sales_cycle: SalesCycle


# --- D · What is rotting -----------------------------------------------------


class ListQuery(BaseModel):
    """The request that lists what a count counted, so a client links to it
    without re-deriving the filter.

    `field` names the list inside the response when the endpoint returns
    several, as /briefing/ does.
    """

    path: str
    params: dict[str, str] = {}
    field: str | None = None


class AttentionRow(BaseModel):
    count: int
    list: ListQuery
    # Calendar days the oldest one has waited; only where age is the point.
    oldest_days: int | None = None


class AttentionMetrics(BaseModel):
    """Now. Rows that need later work are not fields yet: lost deals due for
    a revisit (#118) and contacts awaiting a reply (#135)."""

    # Open, nothing planned, no open task. The briefing's definition.
    stalled_deals: AttentionRow
    # Open, expected close date before today.
    overdue_deals: AttentionRow
    overdue_tasks: AttentionRow
    # Planned before today, never marked as happened.
    unconfirmed_interactions: AttentionRow
    captures_waiting: AttentionRow


# --- E · Am I doing the work -------------------------------------------------


class InteractionKindCount(BaseModel):
    kind: InteractionKind
    count: int


class ActivityMetrics(BaseModel):
    """In the period. Outbound vs inbound waits for #135. Tasks completed
    waits for a completion timestamp — `done` says whether, not when."""

    # Interactions that happened in the period, every kind, zeros included.
    interactions_by_kind: list[InteractionKindCount]
    deals_opened: int
    # Captures triaged in the period, by outcome.
    captures_converted: int
    captures_dismissed: int
    tasks_created: int


# --- Trends -------------------------------------------------------------------


class WeekCount(BaseModel):
    # Monday of the ISO week, in the operator's timezone.
    start: date
    count: int
    # False for the week still running: its count is so far, not final.
    complete: bool


class TrendMetrics(BaseModel):
    """A fixed window, independent of `period`: the last ten calendar weeks (WEEKS),
    oldest first, ending with the current one. Weeks with nothing are zeros,
    so the series has no gaps a chart would have to guess about."""

    deals_opened_weekly: list[WeekCount]


class DashboardMetrics(BaseModel):
    period: PeriodRead
    pipeline: PipelineMetrics
    velocity: VelocityMetrics
    attention: AttentionMetrics
    activity: ActivityMetrics
    trends: TrendMetrics
