import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, Request
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    InvalidPasswordException,
    UUIDIDMixin,
    schemas,
)
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from fastapi_users.exceptions import UserInactive
from fastapi_users.jwt import generate_jwt
from sqlalchemy import DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base, get_session
from app.mail import (
    MailDeliveryError,
    MailNotConfiguredError,
    MailSender,
    get_mail_sender,
    invite_mail,
    reset_mail,
)
from app.schemas.user import MIN_PASSWORD_LENGTH

logger = logging.getLogger(__name__)


class User(SQLAlchemyBaseUserTableUUID, Base):
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


async def get_user_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, UUID], None]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = settings.jwt_secret
    reset_password_token_lifetime_seconds = settings.password_token_lifetime_seconds
    verification_token_secret = settings.jwt_secret

    def __init__(
        self,
        user_db: SQLAlchemyUserDatabase[User, UUID],
        mail_sender: MailSender | None = None,
    ) -> None:
        super().__init__(user_db)
        self.mail_sender = mail_sender

    def password_token(self, user: User) -> str:
        """A token for POST /auth/reset-password — the same one forgot_password()
        issues, built the same way, so an invite and a reset redeem identically.

        `password_fgpt` binds it to the current password hash: the first reset
        replaces the hash, and every token issued before it stops working.
        """
        token_data = {
            "sub": str(user.id),
            "password_fgpt": self.password_helper.hash(user.hashed_password),
            "aud": self.reset_password_token_audience,
        }
        return generate_jwt(
            token_data,
            self.reset_password_token_secret,
            self.reset_password_token_lifetime_seconds,
        )

    async def send_invite(self, user: User) -> None:
        """Mail a new account its set-your-password link.

        Raises rather than logs: the caller is the operator at the CLI, who needs
        to know the invite did not go out.
        """
        if not user.is_active:
            raise UserInactive()
        if self.mail_sender is None:
            raise MailNotConfiguredError(
                "mail is not configured; set " + ", ".join(settings.missing_mail_settings())
            )
        await self.mail_sender.send(invite_mail(user.email, user.name, self.password_token(user)))
        logger.info("Invite sent to user %s", user.id)

    async def validate_password(self, password: str, user: schemas.UC | User) -> None:
        # fastapi-users accepts any password by default; without this the reset
        # flow would bypass the rule the change endpoint enforces.
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidPasswordException(
                reason=f"Password should be at least {MIN_PASSWORD_LENGTH} characters"
            )

    # The token hooks log that something happened, never the token itself: it is
    # a credential, and logs end up in places a mailbox does not.
    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        """Mail the reset link. Never raises.

        POST /auth/forgot-password answers 202 for unknown addresses without
        reaching this hook. An error escaping here would turn that into a 500
        for known ones only — telling an outsider which accounts exist. So a
        failed delivery is the operator's problem, reported in the log.
        """
        if self.mail_sender is None:
            logger.warning(
                "Password reset requested for user %s, but mail is not configured (%s)",
                user.id,
                ", ".join(settings.missing_mail_settings()),
            )
            return
        try:
            await self.mail_sender.send(reset_mail(user.email, user.name, token))
        except MailDeliveryError as exc:
            logger.error("Password reset mail for user %s not sent: %s", user.id, exc)
            return
        logger.info("Password reset mail sent to user %s", user.id)

    async def on_after_reset_password(self, user: User, request: Request | None = None) -> None:
        # The token only ever travelled by mail, so redeeming it proves the
        # address — which is all verification means here.
        await self.user_db.update(
            user, {"password_changed_at": datetime.now(UTC), "is_verified": True}
        )
        logger.info("Password reset completed for user %s", user.id)

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        logger.info("Email verification requested for user %s", user.id)

    async def on_after_verify(self, user: User, request: Request | None = None) -> None:
        logger.info("Email verified for user %s", user.id)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, UUID] = Depends(get_user_db),
    mail_sender: MailSender | None = Depends(get_mail_sender),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db, mail_sender)


bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[User, UUID]:
    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=settings.jwt_lifetime_seconds)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
