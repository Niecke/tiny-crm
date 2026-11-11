"""The credential check for /v1/agent/*: an API token, and nothing else (#320).

See app/auth/api_tokens.py for the design. This dependency is used by the
agent router only. A session JWT is refused here, and a token is refused by
`current_active_user` — the two never meet.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_tokens import TOKEN_PREFIX, find_active
from app.auth.users import User
from app.db import get_session

bearer_scheme = HTTPBearer(auto_error=False, description="An API token: `tc_live_…`")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# `last_used_at` is written at most this often per token, so reading is not
# a write per request.
LAST_USED_RESOLUTION = timedelta(seconds=60)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_token_user(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_header),
    db: AsyncSession = Depends(get_session),
) -> User:
    raw = None
    if bearer is not None and bearer.credentials.startswith(TOKEN_PREFIX):
        raw = bearer.credentials
    elif api_key is not None and api_key.startswith(TOKEN_PREFIX):
        raw = api_key
    if raw is None:
        raise _unauthorized()

    token = await find_active(db, raw)
    if token is None or "read" not in token.scopes:
        raise _unauthorized()
    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()

    now = datetime.now(UTC)
    if token.last_used_at is None or now - token.last_used_at > LAST_USED_RESOLUTION:
        token.last_used_at = now
        await db.commit()
    # For the access log; never the token itself.
    request.state.api_token_id = token.id
    return user
