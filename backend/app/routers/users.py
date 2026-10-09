from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import current_active_user, mfa
from app.auth.sessions import close_sessions
from app.auth.throttle import claim_login_attempt, clear_login
from app.auth.users import User, UserManager, current_session_id, get_user_manager
from app.ratelimit import enforce_login_rate_limit, locked_out
from app.schemas.user import (
    MfaCode,
    MfaDisable,
    MfaPassword,
    MfaRecoveryCodes,
    MfaSetup,
    PasswordChange,
    UserRead,
)

# The account's own endpoints. Deliberately no PATCH /users/me: nothing about an
# account is editable except the password, and that needs the old one — and
# two-factor sign-in, which needs the password or a code to change.
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_me(user: User = Depends(current_active_user)) -> User:
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange,
    user: User = Depends(current_active_user),
    session_id: UUID = Depends(current_session_id),
    user_manager: UserManager = Depends(get_user_manager),
) -> None:
    """Change the password and sign out every other session.

    This one stays signed in: the caller just proved they know the password.
    Every other device has to sign in again with the new one — which is the
    point when the reason for the change is a lost laptop.
    """
    verified, _ = user_manager.password_helper.verify_and_update(
        body.old_password, user.hashed_password
    )
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OLD_PASSWORD")

    await user_manager.validate_password(body.new_password, user)
    new_hash = user_manager.password_helper.hash(body.new_password)
    await user_manager.user_db.update(
        user,
        {"hashed_password": new_hash, "password_changed_at": datetime.now(UTC)},
    )
    await close_sessions(user_manager.db, user.id, keep=session_id)


def _check_password(user_manager: UserManager, user: User, password: str) -> None:
    verified, _ = user_manager.password_helper.verify_and_update(password, user.hashed_password)
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PASSWORD_INCORRECT")


async def _claim_guess(request: Request, user_manager: UserManager, user: User) -> None:
    """Charge a password or code check to the account's login backoff.

    The same budget as signing in (app/auth/throttle.py): a stolen session
    cannot guess here faster than at the login form. A success clears it.
    """
    retry_after = await claim_login_attempt(user_manager.db, user.email)
    if retry_after is not None:
        raise locked_out(request, retry_after)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


# Two-factor sign-in (app/auth/mfa.py has the design). Setup and confirm need
# no password: the caller is signed in, and nothing changes for them until a
# code from the new authenticator proves it works. Turning it on or off ends
# every other session, as a password change does.


@router.post("/me/mfa/setup", response_model=MfaSetup)
async def start_mfa_setup(
    user: User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
) -> MfaSetup:
    """Store a new pending secret, replacing any earlier unconfirmed one."""
    if mfa.is_enabled(user):
        raise _conflict("MFA_ALREADY_ENABLED")
    secret = mfa.new_secret()
    if not await mfa.begin_setup(user_manager.db, user.id, mfa.seal(secret)):
        raise _conflict("MFA_ALREADY_ENABLED")
    return MfaSetup(secret=secret, otpauth_uri=mfa.provisioning_uri(user.email, secret))


@router.post("/me/mfa/confirm", response_model=MfaRecoveryCodes)
async def confirm_mfa_setup(
    body: MfaCode,
    user: User = Depends(current_active_user),
    session_id: UUID = Depends(current_session_id),
    user_manager: UserManager = Depends(get_user_manager),
) -> MfaRecoveryCodes:
    """Turn MFA on with the first code from the authenticator."""
    if mfa.is_enabled(user):
        raise _conflict("MFA_ALREADY_ENABLED")
    secret = mfa.unseal(user.mfa_secret) if user.mfa_secret else None
    if secret is None:
        raise _conflict("MFA_SETUP_NOT_STARTED")
    step = mfa.matching_step(secret, body.code)
    if step is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA_CODE_INVALID")
    codes = await mfa.enable(user_manager.db, user, step)
    if codes is None:
        # Another setup replaced the secret this code was checked against.
        raise _conflict("MFA_SETUP_CHANGED")
    await close_sessions(user_manager.db, user.id, keep=session_id)
    return MfaRecoveryCodes(recovery_codes=codes)


@router.post(
    "/me/mfa/recovery-codes",
    response_model=MfaRecoveryCodes,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def replace_recovery_codes(
    request: Request,
    body: MfaPassword,
    user: User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
) -> MfaRecoveryCodes:
    """A fresh set of recovery codes; the old set stops working."""
    if not mfa.is_enabled(user):
        raise _conflict("MFA_NOT_ENABLED")
    await _claim_guess(request, user_manager, user)
    _check_password(user_manager, user, body.password)
    await clear_login(user_manager.db, user.email)
    codes = await mfa.replace_recovery_codes(user_manager.db, user.id)
    return MfaRecoveryCodes(recovery_codes=codes)


@router.post(
    "/me/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def disable_mfa(
    request: Request,
    body: MfaDisable,
    user: User = Depends(current_active_user),
    session_id: UUID = Depends(current_session_id),
    user_manager: UserManager = Depends(get_user_manager),
) -> None:
    """Turn MFA off. Needs both factors: a stolen session alone cannot."""
    if not mfa.is_enabled(user):
        raise _conflict("MFA_NOT_ENABLED")
    await _claim_guess(request, user_manager, user)
    _check_password(user_manager, user, body.password)
    if not await mfa.claim_code(user_manager.db, user, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA_CODE_INVALID")
    await clear_login(user_manager.db, user.email)
    await mfa.disable(user_manager.db, user.id)
    await close_sessions(user_manager.db, user.id, keep=session_id)
