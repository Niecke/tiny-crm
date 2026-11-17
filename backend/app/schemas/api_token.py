from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, field_validator

ApiTokenStatus = Literal["active", "expired", "revoked"]
ApiTokenScope = Literal["read", "propose"]


class ApiTokenCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    expires_at: AwareDatetime | None = None
    # `read` is always on: a token that could not read could not even look up
    # what to propose changes to.
    scopes: list[ApiTokenScope] = ["read"]

    @field_validator("scopes")
    @classmethod
    def _always_read(cls, value: list[ApiTokenScope]) -> list[ApiTokenScope]:
        return ["read", "propose"] if "propose" in value else ["read"]

    @field_validator("expires_at")
    @classmethod
    def _in_the_future(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("expires_at must be in the future")
        return value


class ApiTokenRead(BaseModel):
    id: UUID
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    # Worked out on the server, so the client needs no clock logic of its own.
    status: ApiTokenStatus


class ApiTokenCreated(ApiTokenRead):
    """The only response that ever carries the secret."""

    token: str = Field(description="The raw token. Shown once; only its hash is kept.")
