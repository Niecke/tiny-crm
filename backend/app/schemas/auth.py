from typing import Literal

from pydantic import BaseModel, Field


class TokenPair(BaseModel):
    """What a login or a refresh hands out (app/auth/sessions.py)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    # Seconds until the access token expires. A client renews it shortly before
    # that rather than waiting for a 401.
    expires_in: int
    refresh_token: str


class RefreshTokenBody(BaseModel):
    refresh_token: str = Field(min_length=1)


class MfaChallenge(BaseModel):
    """What a login answers instead of a TokenPair when the account has MFA on
    (app/auth/mfa.py). Trade `mfa_token` and a code at /auth/jwt/mfa."""

    mfa_required: Literal[True] = True
    mfa_token: str
    # Seconds until the challenge expires and the password is needed again.
    expires_in: int


class MfaVerifyBody(BaseModel):
    mfa_token: str = Field(min_length=1)
    # Six digits from the authenticator, or a recovery code.
    code: str = Field(min_length=1, max_length=64)
