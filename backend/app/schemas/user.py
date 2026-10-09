from datetime import datetime
from uuid import UUID

from fastapi_users import schemas as fu_schemas
from pydantic import BaseModel, Field

# One rule for every way a password gets set: the change endpoint enforces it in
# its schema, UserManager.validate_password for password reset and the CLI.
MIN_PASSWORD_LENGTH = 8


class UserRead(fu_schemas.BaseUser[UUID]):
    name: str | None = None
    password_changed_at: datetime | None = None
    # When two-factor sign-in was turned on; None while it is off.
    mfa_enabled_at: datetime | None = None


class UserCreate(fu_schemas.BaseUserCreate):
    """Only the CLI creates accounts (app/cli.py); there is no register route."""

    name: str | None = None


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class MfaSetup(BaseModel):
    """A pending secret: shown as a QR code, confirmed with its first code."""

    secret: str
    otpauth_uri: str


class MfaCode(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class MfaPassword(BaseModel):
    password: str = Field(min_length=1)


class MfaDisable(BaseModel):
    password: str = Field(min_length=1)
    # A code from the authenticator, or a recovery code.
    code: str = Field(min_length=1, max_length=64)


class MfaRecoveryCodes(BaseModel):
    """Shown once. Only their hashes are kept."""

    recovery_codes: list[str]
