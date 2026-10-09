import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.router.common import ErrorCode, ErrorModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa
from app.auth.sessions import close_session, close_sessions, open_session, rotate_session
from app.auth.throttle import claim_login_attempt, clear_login
from app.auth.users import UserManager, get_user_manager
from app.db import get_session
from app.ratelimit import enforce_login_rate_limit, locked_out
from app.schemas.auth import MfaChallenge, MfaVerifyBody, RefreshTokenBody, TokenPair

# Sign-in, token renewal and sign-out (app/auth/sessions.py has the design).
# Replaces fastapi-users' auth router, whose login hands out one token and whose
# logout cannot revoke anything. Same paths, same login form and errors, so the
# login throttle and the OAuth2 flow in /docs keep working.
router = APIRouter(prefix="/auth/jwt", tags=["auth"])

logger = logging.getLogger(__name__)

_REFRESH_REJECTED = "REFRESH_TOKEN_INVALID"
_MFA_TOKEN_REJECTED = "MFA_TOKEN_INVALID"
_MFA_CODE_REJECTED = "MFA_CODE_INVALID"


@router.post(
    "/login",
    response_model=TokenPair | MfaChallenge,
    responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorModel}},
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    db: AsyncSession = Depends(get_session),
) -> TokenPair | MfaChallenge:
    # Refused before the password is looked at: while locked, even the right
    # one gets no answer about itself. Otherwise the attempt is counted as a
    # failure here, up front, so requests arriving together cannot all slip
    # past the lock; a successful login takes it back below.
    retry_after = await claim_login_attempt(db, credentials.username)
    if retry_after is not None:
        raise locked_out(request, retry_after)

    user = await user_manager.authenticate(credentials)
    # One answer for a wrong password and a deactivated account, as in
    # fastapi-users: the difference would tell a guesser the password was right.
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ErrorCode.LOGIN_BAD_CREDENTIALS
        )
    # With MFA on, the password is only half of it: no session yet, and the
    # attempt stays counted until the code is right too, so a known password
    # does not reset the backoff on code guesses.
    if mfa.is_enabled(user):
        return MfaChallenge(
            mfa_token=mfa.issue_mfa_token(user),
            expires_in=int(mfa.MFA_TOKEN_LIFETIME.total_seconds()),
        )
    await clear_login(db, credentials.username)
    tokens = await open_session(db, user.id)
    await user_manager.on_after_login(user, request)
    return tokens


# The second step of a login with MFA on (app/auth/mfa.py). Same throttles as
# the password step: a wrong code is a 400 the per-address limit counts, and
# each attempt is charged to the account's backoff before the code is checked.
@router.post(
    "/mfa",
    response_model=TokenPair,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorModel},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorModel},
    },
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def verify_mfa(
    request: Request,
    body: MfaVerifyBody,
    user_manager: UserManager = Depends(get_user_manager),
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    claims = mfa.read_mfa_token(body.mfa_token)
    user = await user_manager.user_db.get(claims.user_id) if claims else None
    # Expired, forged, or for an MFA setup that has since been replaced or
    # turned off: start over from the password.
    if (
        claims is None
        or user is None
        or not user.is_active
        or not mfa.challenge_matches(user, claims)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_MFA_TOKEN_REJECTED)

    retry_after = await claim_login_attempt(db, user.email)
    if retry_after is not None:
        raise locked_out(request, retry_after)
    if not await mfa.claim_code(db, user, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_MFA_CODE_REJECTED)

    await clear_login(db, user.email)
    tokens = await open_session(db, user.id)
    await user_manager.on_after_login(user, request)
    return tokens


# Not behind the login throttle: a refresh token cannot be guessed, and a
# neighbour on the same address mistyping a password should not sign the
# operator out.
@router.post(
    "/refresh",
    response_model=TokenPair,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorModel}},
)
async def refresh(
    body: RefreshTokenBody,
    user_manager: UserManager = Depends(get_user_manager),
    db: AsyncSession = Depends(get_session),
) -> TokenPair:
    rotated = await rotate_session(db, body.refresh_token)
    if rotated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_REFRESH_REJECTED)
    # The sessions table cascades from the user, so the account exists; it may
    # have been deactivated since the login, though.
    user = await user_manager.get(rotated.user_id)
    if not user.is_active:
        await close_sessions(db, user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_REFRESH_REJECTED)
    return rotated.tokens


# Takes the refresh token rather than the access token, so a tab whose access
# token has already expired can still sign out properly. Always 204: signing
# out of a session that is already gone has nothing to report.
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def logout(body: RefreshTokenBody, db: AsyncSession = Depends(get_session)) -> None:
    await close_session(db, body.refresh_token)
