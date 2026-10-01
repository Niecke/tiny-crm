from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import current_active_user
from app.auth.sessions import close_sessions
from app.auth.users import User, UserManager, current_session_id, get_user_manager
from app.schemas.user import PasswordChange, UserRead

# The account's own endpoints. Deliberately no PATCH /users/me: nothing about an
# account is editable except the password, and that needs the old one.
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
