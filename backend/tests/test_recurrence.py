"""The recurrence arithmetic, away from the database.

The interesting cases are calendar edges (month-end, leap day) and the rule
that a late completion re-anchors instead of walking the missed slots forward.
"""

from datetime import UTC, datetime

import pytest

from app.recurrence import advance, next_due_date


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_each_rule_steps_by_its_own_unit() -> None:
    start = at("2026-03-10T09:00")

    assert advance(start, "daily", 1) == at("2026-03-11T09:00")
    assert advance(start, "weekly", 2) == at("2026-03-24T09:00")
    assert advance(start, "monthly", 3) == at("2026-06-10T09:00")
    assert advance(start, "yearly", 1) == at("2027-03-10T09:00")


def test_a_month_step_clamps_to_the_end_of_a_shorter_month() -> None:
    assert advance(at("2026-01-31T09:00"), "monthly", 1) == at("2026-02-28T09:00")
    assert advance(at("2024-01-31T09:00"), "monthly", 1) == at("2024-02-29T09:00")
    assert advance(at("2024-02-29T09:00"), "yearly", 1) == at("2025-02-28T09:00")


def test_an_interval_below_one_is_refused() -> None:
    with pytest.raises(ValueError):
        advance(at("2026-03-10T09:00"), "daily", 0)


def test_finishing_on_time_keeps_the_original_cadence() -> None:
    # Due on the 1st, ticked off two days early: still due on the 1st next month.
    assert next_due_date(
        at("2026-03-01T23:59"), "monthly", 1, completed_at=at("2026-02-27T10:00")
    ) == at("2026-04-01T23:59")


def test_finishing_late_re_anchors_on_the_completion() -> None:
    # A monthly check-in last due in March, actually done in June, is due again
    # in July — one instance, not the four slots that were missed.
    assert next_due_date(
        at("2026-03-01T23:59"), "monthly", 1, completed_at=at("2026-06-15T14:30")
    ) == at("2026-07-15T23:59")


def test_a_long_overdue_task_produces_exactly_one_future_instance() -> None:
    completed_at = at("2026-06-15T14:30")

    following = next_due_date(at("2025-01-05T08:00"), "daily", 1, completed_at=completed_at)

    assert following == at("2026-06-16T08:00")


def test_the_series_stops_at_recurrence_until() -> None:
    due_date, completed_at = at("2026-03-01T23:59"), at("2026-03-01T18:00")

    assert next_due_date(due_date, "monthly", 1, completed_at, until=at("2026-03-31T23:59")) is None
    # Inclusive: an occurrence landing exactly on the end date still happens.
    assert next_due_date(due_date, "monthly", 1, completed_at, until=at("2026-04-01T23:59")) == at(
        "2026-04-01T23:59"
    )


def test_naive_timestamps_are_read_as_utc() -> None:
    following = next_due_date(
        datetime(2026, 3, 1, 23, 59), "weekly", 1, completed_at=datetime(2026, 3, 1, 18, 0)
    )

    assert following == at("2026-03-08T23:59")
