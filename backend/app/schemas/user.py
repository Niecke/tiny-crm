from uuid import UUID

from fastapi_users import schemas as fu_schemas
from pydantic import BaseModel, Field


class UserRead(fu_schemas.BaseUser[UUID]):
    pass


class UserUpdate(fu_schemas.BaseUserUpdate):
    pass


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
