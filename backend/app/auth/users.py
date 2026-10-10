import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    InvalidPasswordException,
    UUIDIDMixin,
    exceptions,
    schemas,
)
from fastapi_users.authentication import AuthenticationBackend, BearerTransport
from fastapi_users.authentication.strategy import StrategyDestroyNotSupportedError
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from fastapi_users.exceptions import UserInactive
from fastapi_users.jwt import generate_jwt
from procrastinate.exceptions import AlreadyEnqueued, ProcrastinateException
from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.sessions import close_sessions, read_access_token, session_is_open
from app.auth.throttle import claim_reset_mail, clear_login
from app.config import settings
from app.db import Base, get_session
from app.mail import MailNotConfiguredError, MailSender, get_mail_sender, invite_mail
from app.schemas.user import MIN_PASSWORD_LENGTH

logger = logging.getLogger(__name__)


class User(SQLAlchemyBaseUserTableUUID, Base):
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Two-factor sign-in (app/auth/mfa.py). The secret is sealed, never plain;
    # set without `mfa_enabled_at` it is a setup still waiting for its first code.
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The TOTP time step last accepted, so a code is good once.
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


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
        # The request's own session, for the sessions table (app/auth/sessions.py).
        self.db = user_db.session
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
        """Queue the reset mail for the worker (app/jobs/mail.py). Never raises.

        Nothing is sent from here. Waiting for Brevo inside the request made a
        known address answer seconds later than an unknown one, which told an
        outsider which accounts exist just as a different status would have. Now
        both get their 202 in the time of a couple of inserts.

        `token` is not used: the worker mints its own when it sends, so no
        credential sits in the job table (see send_password_reset).

        For the same reason as the timing, no error may escape: POST
        /auth/forgot-password answers 202 for unknown addresses without reaching
        this hook, and a 500 for known ones only would give them away. A mail
        that could not be queued is the operator's problem, reported in the log.

        At most one mail per PASSWORD_RESET_COOLDOWN_SECONDS (#134), claimed
        before queueing so a failed delivery costs one too. Inside the cooldown
        the request is dropped and still answered 202: the mail already sent is
        the one to use.
        """
        # Imported here: the job module needs this one for UserManager.
        from app.jobs.mail import reset_lock, send_password_reset

        if not await claim_reset_mail(self.db, user.email):
            logger.info("Password reset for user %s skipped: mail cooldown running", user.id)
            return
        if self.mail_sender is None:
            logger.warning(
                "Password reset requested for user %s, but mail is not configured (%s)",
                user.id,
                ", ".join(settings.missing_mail_settings()),
            )
            return
        try:
            await send_password_reset.configure(queueing_lock=reset_lock(user.id)).defer_async(
                user_id=str(user.id), requested_at=datetime.now(UTC).isoformat()
            )
        except AlreadyEnqueued:
            # A mail for this account is still waiting — the cooldown has run
            # out while the worker is behind or retrying. That one will do.
            logger.info("Password reset for user %s skipped: a mail is already queued", user.id)
            return
        except ProcrastinateException as exc:
            logger.error(
                "Password reset mail for user %s not queued: %s", user.id, type(exc).__name__
            )
            return
        logger.info("Password reset mail queued for user %s", user.id)

    async def on_after_reset_password(self, user: User, request: Request | None = None) -> None:
        # The token only ever travelled by mail, so redeeming it proves the
        # address — which is all verification means here.
        await self.user_db.update(
            user, {"password_changed_at": datetime.now(UTC), "is_verified": True}
        )
        # Whoever reset the password may not be whoever is signed in: every
        # session ends, including any the old password opened.
        await close_sessions(self.db, user.id)
        # Whoever could redeem the link controls the mailbox; any backoff the
        # forgotten password ran up is theirs to drop.
        await clear_login(self.db, user.email)
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


class SessionStrategy:
    """Reads access tokens for fastapi-users' current_user dependency.

    Unlike fastapi-users' JWTStrategy, a valid signature is not enough: the
    token's session must still exist, so a signed-out token is dead at once.
    Tokens are issued by app/routers/auth.py, not through this class.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def read_token(
        self, token: str | None, user_manager: BaseUserManager[User, UUID]
    ) -> User | None:
        claims = read_access_token(token) if token else None
        if claims is None or not await session_is_open(self.db, claims):
            return None
        try:
            return await user_manager.get(claims.user_id)
        except exceptions.UserNotExists:
            return None

    async def write_token(self, user: User) -> str:
        raise NotImplementedError("tokens are issued by app.auth.sessions.open_session")

    async def destroy_token(self, token: str, user: User) -> None:
        raise StrategyDestroyNotSupportedError("sign-out is POST /auth/jwt/logout")


def get_session_strategy(db: AsyncSession = Depends(get_session)) -> SessionStrategy:
    return SessionStrategy(db)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_session_strategy,
)

fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)


async def current_session_id(
    token: str = Depends(bearer_transport.scheme),
    user: User = Depends(current_active_user),
) -> UUID:
    """The session the request's access token belongs to, for sign-out-others."""
    claims = read_access_token(token)
    if claims is None:  # pragma: no cover — current_active_user already checked it
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return claims.session_id
