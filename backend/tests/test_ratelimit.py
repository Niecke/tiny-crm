"""Unit tests for the login throttle's sliding window.

Timestamps are written straight into the module's state where a test needs the
clock to have moved, so nothing here sleeps.
"""

import time
from collections import deque
from collections.abc import Iterator

import pytest

from app import ratelimit
from app.config import settings


@pytest.fixture(autouse=True)
def clean_counters() -> Iterator[None]:
    ratelimit._failures.clear()
    ratelimit._last_sweep = 0.0
    yield
    ratelimit._failures.clear()


def test_an_address_is_allowed_until_its_budget_is_spent() -> None:
    for _ in range(settings.login_max_failures - 1):
        ratelimit.record_failed_login("10.0.0.1")
    assert ratelimit.retry_after_seconds("10.0.0.1") is None

    ratelimit.record_failed_login("10.0.0.1")

    retry_after = ratelimit.retry_after_seconds("10.0.0.1")
    assert retry_after is not None
    assert 0 < retry_after <= settings.login_failure_window_seconds + 1


def test_budgets_do_not_leak_between_addresses() -> None:
    for _ in range(settings.login_max_failures):
        ratelimit.record_failed_login("10.0.0.1")

    assert ratelimit.retry_after_seconds("10.0.0.2") is None


def test_an_untracked_address_is_allowed() -> None:
    assert ratelimit.retry_after_seconds("10.0.0.9") is None


def test_failures_age_out_of_the_window() -> None:
    stale = time.monotonic() - settings.login_failure_window_seconds - 1
    ratelimit._failures["10.0.0.3"] = deque([stale] * settings.login_max_failures)

    assert ratelimit.retry_after_seconds("10.0.0.3") is None


def test_a_partly_expired_window_still_blocks() -> None:
    now = time.monotonic()
    stale = now - settings.login_failure_window_seconds - 1
    recent = [now] * settings.login_max_failures
    ratelimit._failures["10.0.0.4"] = deque([stale, *recent])

    assert ratelimit.retry_after_seconds("10.0.0.4") is not None
