"""Two-factor sign-in with an authenticator app (#18).

**Turning it on.** POST /users/me/mfa/setup stores a fresh TOTP secret on the
account, *pending*: `mfa_secret` is set, `mfa_enabled_at` is not, and sign-in
ignores it. The app shows it as a QR code; POST /users/me/mfa/confirm with the
first code the authenticator shows sets `mfa_enabled_at`, so a secret that
never reached a phone cannot lock anyone out. Confirming also issues the
recovery codes, shown once.

**Signing in.** With MFA on, a correct password no longer opens a session.
/auth/jwt/login answers with a challenge instead — an `mfa_token`, a JWT
naming the user, valid for MFA_TOKEN_LIFETIME — and /auth/jwt/mfa trades that
token plus a code for the usual token pair. The challenge token has its own
audience, so it is never accepted as an access token, and it carries a
fingerprint of the stored secret, so turning MFA off and on again voids any
challenge issued before.

Code guesses are charged to the same per-account backoff as password guesses
(app/auth/throttle.py), and the backoff is only cleared once the second step
succeeds: knowing the password buys no free code guesses.

**Codes.** Six digits, 30-second steps, one step of clock drift either way. A
code is good once: the step it matched is stored in `mfa_last_step`, and that
step or an earlier one is refused afterwards, in one conditional UPDATE so two
requests racing with the same code cannot both win.

**Recovery codes.** RECOVERY_CODE_COUNT single-use codes, each usable where a
TOTP code is. Only their SHA-256 is stored, like the calendar feed token.
Issuing a new set replaces the old one. Last resort for a lost phone *and* lost
codes: `python -m app.cli disable-mfa <email>` on the server.

**The secret at rest** is encrypted with a key derived from JWT_SECRET, so a
database dump alone does not hand out working authenticators. Rotating
JWT_SECRET therefore makes every stored secret unreadable: those accounts sign
in with a recovery code (or the CLI turns MFA off) and set it up again.

**Password reset** leaves MFA on: a reset proves control of the mailbox, which
is exactly what a second factor is meant not to rely on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid4

import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi_users.jwt import decode_jwt, generate_jwt
from sqlalchemy import DateTime, ForeignKey, String, delete, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.users import User
from app.config import settings
from app.db import Base

ISSUER = "tinyCRM"
MFA_TOKEN_AUDIENCE = ["tinycrm:mfa"]
MFA_TOKEN_LIFETIME = timedelta(minutes=5)

RECOVERY_CODE_COUNT = 10
# No 0/o, 1/i/l: the codes get written down and typed back in.
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_RECOVERY_GROUPS = 3
_RECOVERY_GROUP_LENGTH = 4


class MfaRecoveryCode(Base):
    """One single-use recovery code. Deleted with the account or the set."""

    __tablename__ = "mfa_recovery_codes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MfaChallengeClaims(NamedTuple):
    user_id: UUID
    fingerprint: str


def _fernet() -> Fernet:
    # Derived per call rather than at import: the tests replace the secret
    # after this module is loaded.
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"tinycrm:mfa-secret").derive(
        settings.jwt_secret.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def seal(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def unseal(sealed: str) -> str | None:
    """The plain secret; None if it was sealed under another JWT_SECRET."""
    try:
        return _fernet().decrypt(sealed.encode()).decode()
    except InvalidToken:
        return None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(email: str, secret: str) -> str:
    """The otpauth:// URI an authenticator app reads from the QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def is_enabled(user: User) -> bool:
    return user.mfa_enabled_at is not None and user.mfa_secret is not None


def _normalize(code: str) -> str:
    return "".join(c for c in code.lower() if c.isalnum())


def _looks_like_totp(code: str) -> bool:
    return len(code) == 6 and code.isdigit()


def matching_step(secret: str, code: str, now: datetime | None = None) -> int | None:
    """The time step `code` belongs to, allowing one step of drift; None if none."""
    code = _normalize(code)
    if not _looks_like_totp(code):
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(now or datetime.now(UTC))
    for step in (current, current - 1, current + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


async def claim_totp(db: AsyncSession, user: User, code: str) -> bool:
    """Accept a TOTP code for an account with MFA on, at most once per step."""
    if user.mfa_secret is None:
        return False
    secret = unseal(user.mfa_secret)
    if secret is None:
        return False
    step = matching_step(secret, code)
    if step is None:
        return False
    claimed = await db.scalar(
        update(User)
        .where(
            User.id == user.id,  # type: ignore[arg-type]
            or_(User.mfa_last_step.is_(None), User.mfa_last_step < step),
        )
        .values(mfa_last_step=step)
        .returning(User.mfa_last_step)
    )
    await db.commit()
    return claimed is not None


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode()).hexdigest()


def _new_recovery_code() -> str:
    groups = (
        "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_GROUP_LENGTH))
        for _ in range(_RECOVERY_GROUPS)
    )
    return "-".join(groups)


async def replace_recovery_codes(db: AsyncSession, user_id: UUID) -> list[str]:
    """A fresh set of recovery codes; every earlier one stops working."""
    codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
    db.add_all(
        MfaRecoveryCode(user_id=user_id, code_hash=_hash_recovery_code(code)) for code in codes
    )
    await db.commit()
    return codes


async def claim_recovery_code(db: AsyncSession, user_id: UUID, code: str) -> bool:
    """Spend one unused recovery code. Conditional, so it is spent only once."""
    spent = await db.scalar(
        update(MfaRecoveryCode)
        .where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.code_hash == _hash_recovery_code(code),
            MfaRecoveryCode.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
        .returning(MfaRecoveryCode.id)
    )
    await db.commit()
    return spent is not None


async def claim_code(db: AsyncSession, user: User, code: str) -> bool:
    """Accept either kind of code: six digits are TOTP, anything else recovery."""
    if _looks_like_totp(_normalize(code)):
        return await claim_totp(db, user, code)
    return await claim_recovery_code(db, user.id, code)


async def enable(db: AsyncSession, user: User, step: int) -> list[str]:
    """Turn the pending secret on; the confirming code's step counts as used."""
    await db.execute(
        update(User)
        .where(User.id == user.id)  # type: ignore[arg-type]
        .values(mfa_enabled_at=datetime.now(UTC), mfa_last_step=step)
    )
    return await replace_recovery_codes(db, user.id)


async def disable(db: AsyncSession, user_id: UUID) -> bool:
    """Turn MFA off and forget the secret and codes. True if it was on or pending."""
    result = await db.execute(
        update(User)
        .where(User.id == user_id, User.mfa_secret.is_not(None))  # type: ignore[arg-type]
        .values(mfa_secret=None, mfa_enabled_at=None, mfa_last_step=None)
    )
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id))
    await db.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def _fingerprint(user: User) -> str:
    # The sealed value is re-encrypted with a fresh nonce on every setup, so a
    # new setup changes it even if the same secret came up twice.
    return hashlib.sha256((user.mfa_secret or "").encode()).hexdigest()[:32]


def issue_mfa_token(user: User) -> str:
    return generate_jwt(
        {"sub": str(user.id), "mfa_fgpt": _fingerprint(user), "aud": MFA_TOKEN_AUDIENCE},
        settings.jwt_secret,
        int(MFA_TOKEN_LIFETIME.total_seconds()),
    )


def read_mfa_token(token: str) -> MfaChallengeClaims | None:
    try:
        data = decode_jwt(token, settings.jwt_secret, MFA_TOKEN_AUDIENCE)
        return MfaChallengeClaims(UUID(data["sub"]), str(data["mfa_fgpt"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def challenge_matches(user: User, claims: MfaChallengeClaims) -> bool:
    """Whether a challenge still belongs to the account's current MFA setup."""
    return is_enabled(user) and hmac.compare_digest(claims.fingerprint, _fingerprint(user))
