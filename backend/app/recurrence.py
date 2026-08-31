"""Recurring tasks: the fixed rule set and the next-due-date arithmetic.

Deliberately not RRULE. Four cadences plus an interval cover what a one-person
CRM actually schedules — "check the ORF winners' job pages monthly", "follow up
with EBCONT in two weeks" — and they are a closed set the UI can render as a
dropdown. If a real case turns up that needs "every second Tuesday", the column
can grow into an RRULE string without changing how completion spawns the next
instance.
"""

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

RecurrenceRule = Literal["daily", "weekly", "monthly", "yearly"]

RECURRENCE_RULES: tuple[str, ...] = get_args(RecurrenceRule)

# A year of days, a year of weeks, a century of months — past this the interval
# is a typo, not a schedule.
MAX_RECURRENCE_INTERVAL = 366


def _add_months(moment: datetime, months: int) -> datetime:
    """`moment` shifted by whole months, clamped to the end of short months.

    31 January + 1 month is 28 (or 29) February, not 3 March.
    """
    total = moment.month - 1 + months
    year = moment.year + total // 12
    month = total % 12 + 1
    day = min(moment.day, monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def advance(moment: datetime, rule: RecurrenceRule, interval: int) -> datetime:
    """One step of `rule` (times `interval`) forward from `moment`."""
    if interval < 1:
        raise ValueError("recurrence_interval must be at least 1")
    match rule:
        case "daily":
            return moment + timedelta(days=interval)
        case "weekly":
            return moment + timedelta(weeks=interval)
        case "monthly":
            return _add_months(moment, interval)
        case "yearly":
            return _add_months(moment, 12 * interval)


def _as_aware(moment: datetime) -> datetime:
    """Naive timestamps are UTC — the columns are timestamptz, but a caller
    holding a hand-built datetime should not blow up on a mixed comparison."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def next_due_date(
    due_date: datetime,
    rule: RecurrenceRule,
    interval: int,
    completed_at: datetime,
    until: datetime | None = None,
) -> datetime | None:
    """When the instance created by this completion is due, or None if the
    series has run out.

    Finishing on time keeps the cadence: a task due on the 1st, completed on the
    28th of the month before, is next due on the 1st of the following month.

    Finishing *late* re-anchors on the completion instead of walking the missed
    slots forward. A monthly check-in last due in March and ticked off in June
    is next due in July — one instance, not four backdated ones. The time of day
    stays the one the user picked, so an end-of-day task stays end-of-day.

    `until` is inclusive: an occurrence falling exactly on it is still created.
    """
    due_date = _as_aware(due_date)
    completed_at = _as_aware(completed_at)

    scheduled = advance(due_date, rule, interval)
    if scheduled <= completed_at:
        anchor = completed_at.astimezone(due_date.tzinfo).replace(
            hour=due_date.hour,
            minute=due_date.minute,
            second=due_date.second,
            microsecond=due_date.microsecond,
        )
        scheduled = advance(anchor, rule, interval)

    if until is not None and scheduled > _as_aware(until):
        return None
    return scheduled
