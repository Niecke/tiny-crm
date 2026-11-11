"""Create, list and revoke the signed-in user's API tokens (#320).

Session only (`current_active_user`): a token cannot make or revoke tokens.
The token itself is accepted by app/routers/agent.py alone.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.api_tokens import SCOPES, ApiToken, hash_token, new_token
from app.auth.sessions import lock_open_session
from app.auth.users import User, current_session_id
from app.db import get_session
from app.schemas.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenRead, ApiTokenStatus

router = APIRouter(prefix="/users/me/api-tokens", tags=["users"])


def _status(token: ApiToken, now: datetime) -> ApiTokenStatus:
    if token.revoked_at is not None:
        return "revoked"
    if token.expires_at is not None and token.expires_at <= now:
        return "expired"
    return "active"


def _read(token: ApiToken) -> ApiTokenRead:
    return ApiTokenRead(
        id=token.id,
        name=token.name,
        scopes=token.scopes,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        status=_status(token, datetime.now(UTC)),
    )


@router.get("/", response_model=list[ApiTokenRead])
async def list_api_tokens(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> list[ApiTokenRead]:
    """Every token of the caller, newest first, revoked ones included."""
    rows = await session.scalars(
        select(ApiToken)
        .where(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id)
    )
    return [_read(t) for t in rows]


@router.post("/", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_api_token(
    body: ApiTokenCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
    session_id: UUID = Depends(current_session_id),
) -> ApiTokenCreated:
    """Make a token. The raw value is in this response and nowhere else, ever."""
    # Re-check the session under a row lock so a concurrent password reset
    # cannot sweep tokens before this one is committed.
    if not await lock_open_session(session, session_id, user.id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    raw = new_token()
    token = ApiToken(
        user_id=user.id,
        name=body.name,
        token_hash=hash_token(raw),
        scopes=list(SCOPES),
        expires_at=body.expires_at,
    )
    session.add(token)
    await session.commit()
    await session.refresh(token)
    return ApiTokenCreated(**_read(token).model_dump(), token=raw)


@router.post("/{token_id}/revoke", response_model=ApiTokenRead)
async def revoke_api_token(
    token_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ApiTokenRead:
    """End a token. Revoking one that is already revoked keeps the first date."""
    token = await session.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(status_code=404, detail="API token not found")
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(token)
    return _read(token)
