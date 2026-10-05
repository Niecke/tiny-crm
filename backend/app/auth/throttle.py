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
per expiry. An attempt is counted, and its lock set, *before* its password is
checked (claim_login_attempt), under a row lock: of any number of requests
arriving together, only as many reach the password check as arriving one
after another would. It is deliberately not a hard lock: that would hand an attacker a
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

**Limits.** Logins for invented addresses each add a row, swept once they are
a decay window old.

The table is a key, a counter and an expiry by design: moving it to Redis
(#245) replaces this module and drops the table, nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String, delete, or_, select, update
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
    # Indexed for the sweep in claim_login_attempt(), which runs per attempt.
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


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


async def claim_login_attempt(db: AsyncSession, email: str) -> int | None:
    """Count a login attempt for `email` before its password is checked.

    None: the attempt may go ahead, and has been counted as a failure — a
    successful login takes that back through clear_login(). Otherwise the
    account is locked, nothing was counted, and the result is how many seconds
    remain.
    """
    now = datetime.now(UTC)
    decay_cutoff = now - timedelta(seconds=settings.login_backoff_decay_seconds)
    key = _key(_LOGIN, email)

    # Create the row or lock the stored one, and read it, in one statement.
    # The no-op update is what takes the row lock: concurrent attempts on one
    # account queue here, and each sees what the one before it committed.
    statement = insert(AuthThrottle).values(key=key, count=0, last_event_at=now)
    statement = statement.on_conflict_do_update(
        index_elements=[AuthThrottle.key], set_={"key": AuthThrottle.key}
    )
    count: int
    locked_until: datetime | None
    last_event_at: datetime
    count, locked_until, last_event_at = (
        await db.execute(
            statement.returning(
                AuthThrottle.count, AuthThrottle.locked_until, AuthThrottle.last_event_at
            )
        )
    ).one()

    if locked_until is not None and locked_until > now:
        await db.commit()
        return math.ceil((locked_until - now).total_seconds())

    failures = 1 if last_event_at <= decay_cutoff else count + 1
    seconds = lock_seconds(failures)
    await db.execute(
        update(AuthThrottle)
        .where(AuthThrottle.key == key)
        .values(
            count=failures,
            last_event_at=now,
            locked_until=now + timedelta(seconds=seconds) if seconds else None,
        )
    )

    # Nothing else deletes rows that ran out, so counted attempts sweep them,
    # the way a login sweeps expired sessions. SKIP LOCKED: a row another
    # request holds is left for the next sweep rather than waited on.
    stale = (
        select(AuthThrottle.key)
        .where(
            AuthThrottle.key != key,
            AuthThrottle.last_event_at <= decay_cutoff,
            or_(AuthThrottle.locked_until.is_(None), AuthThrottle.locked_until <= now),
        )
        .with_for_update(skip_locked=True)
    )
    await db.execute(delete(AuthThrottle).where(AuthThrottle.key.in_(stale.scalar_subquery())))

    # Committed before the caller hashes a password, so the row lock is never
    # held across that.
    await db.commit()
    return None


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
