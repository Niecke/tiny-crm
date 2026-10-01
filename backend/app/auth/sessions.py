"""Login sessions: a short-lived access token and a refresh token that renews it (#133).

A login opens a row in `auth_sessions`. Both tokens name that row, so deleting
it ends the session everywhere at once: sign-out deletes one, a password change
every other one, a password reset all of them.

**Access token.** A JWT carrying `sub` (the user) and `sid` (the session),
valid for ACCESS_TOKEN_LIFETIME_SECONDS. Every authenticated request also checks
that the session still exists — one primary-key lookup — so a signed-out token
stops working immediately rather than when it expires.

**Refresh token.** `<sid>.<generation>.<mac>`, where the MAC is an HMAC of the
first two parts under JWT_SECRET. Nothing secret is stored: the row keeps only
the current generation, and the token is recomputed to check it. Each refresh
bumps the generation, so a refresh token works once:

  * the current generation rotates to the next one;
  * the one just replaced is still honoured for ROTATION_GRACE and answered
    with the *same* new token — two tabs refreshing together, or a retry after
    a lost response, is not an attack;
  * anything older is a refresh token used twice, i.e. a copy is in someone
    else's hands. The session is deleted, and both holders have to sign in.

Every refresh also pushes the session's expiry out by
REFRESH_TOKEN_LIFETIME_SECONDS, so that lifetime is idle time, not a hard cap.

**Not a session: the calendar feed token (T22, #132).** A subscribed `.ics`
feed cannot send a header or refresh anything, so it gets its own credential,
designed here so the two do not blur:

  * one random token per user (`secrets.token_urlsafe(32)`) in the feed URL's
    path, stored only as its SHA-256 — unlike a refresh token it is not
    derived, so resetting it needs no generation counter;
  * accepted by the feed route alone, and never as a bearer token; the
    access-token check above must not learn about it;
  * read-only by construction: the route serves the feed and nothing else;
  * lives until replaced — "reset feed link" in the account page, and a
    password *reset* (the compromised-account path) replaces it too. A
    password *change* leaves it, like the session that made the change, so a
    routine change does not break every calendar subscription.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid4

import jwt
from fastapi_users.jwt import decode_jwt, generate_jwt
from sqlalchemy import DateTime, ForeignKey, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base
from app.schemas.auth import TokenPair

logger = logging.getLogger(__name__)

# fastapi-users' own audience, kept so the tokens stay recognisably its kind.
ACCESS_TOKEN_AUDIENCE = ["fastapi-users:auth"]

# How long a refresh token that was just rotated away is still answered. Long
# enough for a slow network retry, short enough that a stolen copy used later
# is still caught.
ROTATION_GRACE = timedelta(seconds=60)


class AuthSession(Base):
    """One signed-in device. Deleted, not flagged, when it ends."""

    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    # Which refresh token is current; see the module docstring.
    generation: Mapped[int] = mapped_column(default=0, server_default="0")
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessClaims(NamedTuple):
    user_id: UUID
    session_id: UUID


class Rotated(NamedTuple):
    user_id: UUID
    tokens: TokenPair


def _mac(session_id: UUID, generation: int) -> bytes:
    # The "refresh:" prefix keeps these MACs from ever colliding with anything
    # else signed under the same secret.
    message = f"refresh:{session_id}:{generation}".encode()
    digest = hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=")


def _refresh_token(session_id: UUID, generation: int) -> str:
    return f"{session_id}.{generation}.{_mac(session_id, generation).decode()}"


def _parse_refresh_token(token: str) -> tuple[UUID, int] | None:
    """The session and generation a genuine refresh token names; None if forged."""
    try:
        session_part, generation_part, mac = token.split(".")
        session_id = UUID(session_part)
        generation = int(generation_part)
    except ValueError:
        return None
    if generation < 0 or not hmac.compare_digest(mac.encode(), _mac(session_id, generation)):
        return None
    return session_id, generation


def _tokens(user_id: UUID, session_id: UUID, generation: int) -> TokenPair:
    access = generate_jwt(
        {"sub": str(user_id), "sid": str(session_id), "aud": ACCESS_TOKEN_AUDIENCE},
        settings.jwt_secret,
        settings.access_token_lifetime_seconds,
    )
    return TokenPair(
        access_token=access,
        expires_in=settings.access_token_lifetime_seconds,
        refresh_token=_refresh_token(session_id, generation),
    )


def read_access_token(token: str) -> AccessClaims | None:
    """Who and which session a valid, unexpired access token belongs to.

    Only the signature and expiry are checked here; whether the session still
    exists is `session_is_open`'s question.
    """
    try:
        data = decode_jwt(token, settings.jwt_secret, ACCESS_TOKEN_AUDIENCE)
        # A token without `sid` predates sessions and is not accepted.
        return AccessClaims(UUID(data["sub"]), UUID(data["sid"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


async def session_is_open(db: AsyncSession, claims: AccessClaims) -> bool:
    found = await db.scalar(
        select(AuthSession.id).where(
            AuthSession.id == claims.session_id,
            AuthSession.user_id == claims.user_id,
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    return found is not None


async def open_session(db: AsyncSession, user_id: UUID) -> TokenPair:
    now = datetime.now(UTC)
    # Nothing else deletes a session that simply ran out, so a login sweeps
    # the user's own.
    await db.execute(
        delete(AuthSession).where(AuthSession.user_id == user_id, AuthSession.expires_at <= now)
    )
    session_id = uuid4()
    db.add(
        AuthSession(
            id=session_id,
            user_id=user_id,
            expires_at=now + timedelta(seconds=settings.refresh_token_lifetime_seconds),
        )
    )
    await db.commit()
    return _tokens(user_id, session_id, 0)


async def rotate_session(db: AsyncSession, refresh_token: str) -> Rotated | None:
    """Trade a refresh token for a fresh pair; None if it is no longer good."""
    parsed = _parse_refresh_token(refresh_token)
    if parsed is None:
        return None
    session_id, generation = parsed
    now = datetime.now(UTC)

    # Conditional on the generation, so of two concurrent refreshes exactly one
    # rotates and the other falls through to the grace check below.
    user_id = await db.scalar(
        update(AuthSession)
        .where(
            AuthSession.id == session_id,
            AuthSession.generation == generation,
            AuthSession.expires_at > now,
        )
        .values(
            generation=generation + 1,
            rotated_at=now,
            expires_at=now + timedelta(seconds=settings.refresh_token_lifetime_seconds),
        )
        .returning(AuthSession.user_id)
    )
    if user_id is not None:
        await db.commit()
        return Rotated(user_id, _tokens(user_id, session_id, generation + 1))

    session = await db.get(AuthSession, session_id)
    if session is None or session.expires_at <= now:
        return None
    just_rotated = (
        generation == session.generation - 1
        and session.rotated_at is not None
        and now - session.rotated_at <= ROTATION_GRACE
    )
    if just_rotated:
        return Rotated(session.user_id, _tokens(session.user_id, session_id, session.generation))

    logger.warning(
        "Refresh token for session %s of user %s was used twice; session revoked",
        session_id,
        session.user_id,
    )
    await db.delete(session)
    await db.commit()
    return None


async def close_session(db: AsyncSession, refresh_token: str) -> None:
    """Sign out the session a refresh token belongs to. Silent if there is none."""
    parsed = _parse_refresh_token(refresh_token)
    if parsed is None:
        return
    await db.execute(delete(AuthSession).where(AuthSession.id == parsed[0]))
    await db.commit()


async def close_sessions(db: AsyncSession, user_id: UUID, *, keep: UUID | None = None) -> None:
    """Sign out every session of a user, except `keep` if given."""
    statement = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep is not None:
        statement = statement.where(AuthSession.id != keep)
    await db.execute(statement)
    await db.commit()
