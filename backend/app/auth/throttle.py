"""Durable per-account login backoff and reset-mail cooldown (#134).

The in-memory throttle in app/ratelimit.py counts per source address and
forgets everything on a redeploy. This one follows the *account* and lives in
Postgres, so rotating addresses or waiting for a deploy buys an attacker
nothing.

**Keys.** One row per account and purpose, keyed `<kind>:<HMAC of the
address>`. Nothing references `user`: a login for an address that has no
account is throttled exactly like one that does, so a 429 never tells a
guesser which accounts exist. Only the HMAC is stored, never the address —
nor the password someone typed into the address field by mistake.

**Login backoff.** The first LOGIN_BACKOFF_FREE_FAILURES failures cost
nothing. Each one after that locks the account for 2, 4, 8, … seconds, capped
at LOGIN_BACKOFF_MAX_SECONDS. Attempts while locked are refused before the
password is looked at and do not count, so the lock never grows past one step
per expiry. It is deliberately not a hard lock: that would hand an attacker a
way to keep the operator out for good. Signed-in devices are unaffected —
/auth/jwt/refresh never consults this. A failure more than
LOGIN_BACKOFF_DECAY_SECONDS after the previous one starts counting afresh; a
successful login, a completed password reset and `python -m app.cli unlock`
clear the row.

**Reset-mail cooldown.** One reset mail per account per
PASSWORD_RESET_COOLDOWN_SECONDS. The cooldown is claimed before sending, so a
failed delivery costs one too — a broken mail setup is not retried in a loop.
The caller still answers 202 either way. Only existing accounts reach the
claim, so unknown addresses add no rows.

**Limits.** Requests that arrive together all pass the check before the first
failure is recorded; the per-address throttle bounds that burst. Failed logins
for invented addresses each add a row, swept once they are a decay window old.

Every write is a single upsert, so concurrent requests cannot lose a count.
The table is a key, a counter and an expiry by design: moving it to Redis
(#245) replaces this module and drops the table, nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base

logger = logging.getLogger(__name__)

_LOGIN = "login"
_RESET_MAIL = "reset-mail"


class AuthThrottle(Base):
    __tablename__ = "auth_throttle"

    key: Mapped[str] = mapped_column(String(96), primary_key=True)
    # Failed logins in the current run; unused for the reset-mail cooldown.
    count: Mapped[int] = mapped_column(default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _key(kind: str, email: str) -> str:
    # Case-insensitive like fastapi-users' own lookup, so "Alice@" and "alice@"
    # share one budget. The kind is inside the MAC as well as in front of it,
    # so the two rows of one address are unrelated values.
    address = email.strip().lower()
    message = f"throttle:{kind}:{address}".encode()
    digest = hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()
    return f"{kind}:{digest}"


def lock_seconds(failures: int) -> int:
    """How long `failures` consecutive failed logins lock the account."""
    over = failures - settings.login_backoff_free_failures
    if over <= 0:
        return 0
    # Capped before exponentiating, so a huge count cannot build a huge int.
    cap = settings.login_backoff_max_seconds
    return min(1 << min(over, cap.bit_length()), cap)


async def login_retry_after(db: AsyncSession, email: str) -> int | None:
    """Seconds until `email` may try to log in again, or None if it may now."""
    locked_until = await db.scalar(
        select(AuthThrottle.locked_until).where(AuthThrottle.key == _key(_LOGIN, email))
    )
    if locked_until is None:
        return None
    remaining = (locked_until - datetime.now(UTC)).total_seconds()
    return math.ceil(remaining) if remaining > 0 else None


async def record_login_failure(db: AsyncSession, email: str) -> int:
    """Count a failed login; returns the lock it earned in seconds (0: none)."""
    now = datetime.now(UTC)
    decay_cutoff = now - timedelta(seconds=settings.login_backoff_decay_seconds)

    # Nothing else deletes rows that ran out, so failures sweep them, the way a
    # login sweeps expired sessions. SKIP LOCKED: a row another request holds
    # is left for the next sweep rather than waited on.
    stale = (
        select(AuthThrottle.key)
        .where(
            AuthThrottle.last_event_at <= decay_cutoff,
            or_(AuthThrottle.locked_until.is_(None), AuthThrottle.locked_until <= now),
        )
        .with_for_update(skip_locked=True)
    )
    await db.execute(delete(AuthThrottle).where(AuthThrottle.key.in_(stale.scalar_subquery())))

    key = _key(_LOGIN, email)
    statement = insert(AuthThrottle).values(key=key, count=1, last_event_at=now)
    statement = statement.on_conflict_do_update(
        index_elements=[AuthThrottle.key],
        set_={
            # On the right-hand side, AuthThrottle.* is the row already stored.
            "count": case(
                (AuthThrottle.last_event_at <= decay_cutoff, 1),
                else_=AuthThrottle.count + 1,
            ),
            "last_event_at": now,
        },
    )
    failures = await db.scalar(statement.returning(AuthThrottle.count))
    assert failures is not None  # an upsert always returns its row

    seconds = lock_seconds(failures)
    if seconds:
        until = now + timedelta(seconds=seconds)
        # GREATEST: of two concurrent failures, the smaller count must not
        # shorten the lock the larger one set.
        await db.execute(
            update(AuthThrottle)
            .where(AuthThrottle.key == key)
            .values(
                locked_until=func.greatest(func.coalesce(AuthThrottle.locked_until, until), until)
            )
        )
    await db.commit()
    return seconds


async def clear_login(db: AsyncSession, email: str) -> bool:
    """Forget the failed logins of `email`. True if there were any."""
    result = await db.execute(delete(AuthThrottle).where(AuthThrottle.key == _key(_LOGIN, email)))
    await db.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def claim_reset_mail(db: AsyncSession, email: str) -> bool:
    """Start the reset-mail cooldown of `email`; False if it is still running.

    One statement: the upsert only touches a stored row whose cooldown is over,
    so of two concurrent requests exactly one gets the row back.
    """
    now = datetime.now(UTC)
    until = now + timedelta(seconds=settings.password_reset_cooldown_seconds)
    statement = insert(AuthThrottle).values(
        key=_key(_RESET_MAIL, email), count=0, locked_until=until, last_event_at=now
    )
    statement = statement.on_conflict_do_update(
        index_elements=[AuthThrottle.key],
        set_={"locked_until": until, "last_event_at": now},
        where=or_(AuthThrottle.locked_until.is_(None), AuthThrottle.locked_until <= now),
    )
    claimed = await db.scalar(statement.returning(AuthThrottle.key))
    await db.commit()
    return claimed is not None


async def clear_reset_mail(db: AsyncSession, email: str) -> bool:
    """End the reset-mail cooldown of `email`. True if one was running."""
    result = await db.execute(
        delete(AuthThrottle).where(AuthThrottle.key == _key(_RESET_MAIL, email))
    )
    await db.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]
