from uuid import UUID

from fastapi_users import schemas as fu_schemas


class UserRead(fu_schemas.BaseUser[UUID]):
    pass


class UserUpdate(fu_schemas.BaseUserUpdate):
    pass
