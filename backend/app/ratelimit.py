"""In-memory login throttling.

No cache server is involved: the backend runs as a single uvicorn worker (see
the Dockerfile CMD), so a module-level dict is a process-global counter. Two
consequences to know before changing how the app is served:

  * The window resets on restart, i.e. on every redeploy.
  * Running uvicorn with --workers N multiplies the effective limit by N,
    because every worker keeps its own dict.

Failed logins are what count, not attempts. A successful login consumes no
budget, so someone who mistypes twice and then gets it right is unaffected,
while a password guesser is stopped after `login_max_failures`.

This only throttles per source address. An attacker rotating IPs walks straight
through it — that needs the durable per-account backoff tracked as T34 in PLAN.md.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import RequestResponseEndpoint

from app.config import settings

logger = logging.getLogger(__name__)

LOGIN_PATH = "/auth/jwt/login"

# Client address -> timestamps of its recent failed logins, oldest first.
_failures: dict[str, deque[float]] = {}

# An attacker rotating source addresses would otherwise grow _failures without
# bound, so it is swept periodically and hard-capped.
_MAX_TRACKED_IPS = 10_000
_SWEEP_INTERVAL_SECONDS = 60.0
_last_sweep = 0.0

# fastapi-users answers bad credentials with 400; its 422 is a malformed body,
# which is a client bug rather than a guess, and 429 is our own rejection.
_BAD_CREDENTIALS_STATUS = 400


def _client_ip(request: Request) -> str:
    """The connecting client's address.

    uvicorn's ProxyHeadersMiddleware has already replaced the peer address with
    the real client when the request arrived from a trusted proxy, so reading
    request.client here is correct — provided FORWARDED_ALLOW_IPS names the
    network Caddy connects from. If it does not, every request reports Caddy's
    address and they all share one bucket.
    """
    return request.client.host if request.client else "unknown"


def _prune(timestamps: deque[float], cutoff: float) -> None:
    while timestamps and timestamps[0] <= cutoff:
        timestamps.popleft()


def _sweep(now: float) -> None:
    """Drop addresses whose failures have all aged out of the window."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now

    cutoff = now - settings.login_failure_window_seconds
    for ip in list(_failures):
        _prune(_failures[ip], cutoff)
        if not _failures[ip]:
            del _failures[ip]

    # Still over the cap after sweeping: an active flood from many addresses.
    # Evict the least recently active entries — they are closest to expiring.
    if len(_failures) > _MAX_TRACKED_IPS:
        by_age = sorted(_failures, key=lambda ip: _failures[ip][-1])
        for ip in by_age[: len(_failures) - _MAX_TRACKED_IPS]:
            del _failures[ip]


def record_failed_login(ip: str) -> None:
    now = time.monotonic()
    _sweep(now)
    timestamps = _failures.setdefault(ip, deque())
    _prune(timestamps, now - settings.login_failure_window_seconds)
    timestamps.append(now)


def retry_after_seconds(ip: str) -> int | None:
    """Seconds until `ip` may try again, or None if it is currently allowed."""
    timestamps = _failures.get(ip)
    if timestamps is None:
        return None

    now = time.monotonic()
    window = settings.login_failure_window_seconds
    _prune(timestamps, now - window)
    if len(timestamps) < settings.login_max_failures:
        return None

    # Allowed again once the oldest failure falls out of the window.
    return max(1, int(window - (now - timestamps[0])) + 1)


async def enforce_login_rate_limit(request: Request) -> None:
    """Dependency for the auth router. Rejects addresses over their budget.

    Runs before the handler, so it can only act on failures recorded by earlier
    requests — the counting itself happens in the middleware below.
    """
    ip = _client_ip(request)
    retry_after = retry_after_seconds(ip)
    if retry_after is None:
        return

    logger.warning(
        "Rate-limited login from %s: %d failures within %ds, retry in %ds",
        ip,
        settings.login_max_failures,
        settings.login_failure_window_seconds,
        retry_after,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed login attempts. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


async def count_failed_logins(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Middleware: record and log every rejected login.

    A dependency cannot do this — it runs before the handler and so never sees
    whether the credentials were accepted.
    """
    response: Response = await call_next(request)

    if request.url.path == LOGIN_PATH and response.status_code == _BAD_CREDENTIALS_STATUS:
        ip = _client_ip(request)
        record_failed_login(ip)
        logger.warning(
            "Failed login from %s (%d/%d within %ds)",
            ip,
            len(_failures.get(ip, ())),
            settings.login_max_failures,
            settings.login_failure_window_seconds,
        )

    return response
