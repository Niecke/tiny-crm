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


class UserCreate(fu_schemas.BaseUserCreate):
    """Only the CLI creates accounts (app/cli.py); there is no register route."""

    name: str | None = None


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)
