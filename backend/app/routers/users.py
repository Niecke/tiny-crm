from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import current_active_user
from app.auth.users import User, UserManager, get_user_manager
from app.schemas.user import PasswordChange

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange,
    user: User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
) -> None:
    verified, _ = user_manager.password_helper.verify_and_update(
        body.old_password, user.hashed_password
    )
    if not verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OLD_PASSWORD")

    await user_manager.validate_password(body.new_password, user)
    new_hash = user_manager.password_helper.hash(body.new_password)
    await user_manager.user_db.update(user, {"hashed_password": new_hash})
