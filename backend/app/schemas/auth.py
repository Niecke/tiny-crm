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
