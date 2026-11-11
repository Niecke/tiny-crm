"""API tokens for agents (#320): a read-only credential an operator hands to a tool.

An agent — Claude Code, Cursor, a script — cannot sign in with a password and
MFA, and should not hold a session. It gets a token instead: `tc_live_` plus
256 bits of randomness, shown once when it is made.

  * one token per agent, named by the operator ("pi-agent-desktop"), so one
    can be revoked without touching the others;
  * stored only as its HMAC-SHA256, keyed with the server secret. Unlike a
    password it is not chosen by a human, so a slow hash would add per-request
    latency and no safety. Rotating JWT_SECRET therefore invalidates every
    token, as it does every session;
  * read-only by scope, and accepted by the agent routes alone
    (`current_token_user` in app/auth/agent.py, used only by app/routers/agent.py).
    It is never a bearer for a session: `current_active_user` does not know it,
    so a token cannot reach token management, the password, MFA or any write;
  * ends at `expires_at` if one was set, or when revoked. A password *reset*
    (the compromised-account path) revokes every token; a password *change*
    leaves them, like the feed token, so a routine change does not break
    every agent.

The dependency lives in its own module because it needs `User`, and
app/auth/users.py needs `revoke_all` from here.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func, or_, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base

TOKEN_PREFIX = "tc_live_"
# Part 1 knows one scope. Not settable by the client yet.
SCOPES = ("read",)


class ApiToken(Base):
    """One credential. Revoked, not deleted, so the list shows its history."""

    __tablename__ = "api_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # HMAC-SHA256 hex of the raw token; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{read}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


async def find_active(db: AsyncSession, raw: str) -> ApiToken | None:
    """The token `raw` names, unless it is revoked or past its expiry."""
    now = datetime.now(UTC)
    token: ApiToken | None = await db.scalar(
        select(ApiToken).where(
            ApiToken.token_hash == hash_token(raw),
            ApiToken.revoked_at.is_(None),
            or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now),
        )
    )
    return token


async def revoke_all(db: AsyncSession, user_id: UUID) -> None:
    """End every token of `user_id` that is still in use."""
    await db.execute(
        update(ApiToken)
        .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await db.commit()
