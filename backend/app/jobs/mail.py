"""Mail sent from the worker instead of from the request.

Only request-path mail comes through here. The CLI's invite still sends
directly (UserManager.send_invite): the operator is waiting at the terminal and
needs the failure now, not in a job table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi_users.db import SQLAlchemyUserDatabase
from procrastinate import RetryStrategy

# The whole model registry, not just User: SQLAlchemy configures mappers against
# all of it on first query, and a relationship naming an unimported model fails.
import app.models  # noqa: F401
from app.auth.users import User, UserManager
from app.config import settings
from app.db import _session_factory
from app.jobs import MAIL_QUEUE, jobs_app
from app.mail import MailNotConfiguredError, TransientMailError, get_mail_sender, reset_mail

logger = logging.getLogger(__name__)

# One try and four more, waiting 4, 16, 64 and 256 seconds between them: under
# six minutes in all, which rides out a Brevo hiccup and stays well inside
# MAIL_MAX_AGE_SECONDS. Only for errors that waiting can cure — a refused
# sender or key fails the job at once, where it is visible instead of retried.
MAIL_RETRY = RetryStrategy(
    # procrastinate counts the retries here, not the runs.
    max_attempts=4,
    exponential_wait=4,
    retry_exceptions={TransientMailError},
)


def reset_lock(user_id: UUID) -> str:
    """The queueing lock of an account's reset mail: while one is waiting to be
    sent, asking again cannot stack a second behind it."""
    return f"reset:{user_id}"


@jobs_app.task(name="send_password_reset", queue=MAIL_QUEUE, retry=MAIL_RETRY)
async def send_password_reset(*, user_id: str, requested_at: str) -> None:
    """Mail `user_id` their reset link. Deferred by POST /auth/forgot-password.

    The job carries the account's id and nothing else worth stealing. The token
    is minted here, at send time, and goes into the mail and nowhere else — a
    job row, and the backup it ends up in, never holds a credential. Two things
    follow from that:

    * The link's lifetime starts when the mail leaves, not when it was asked for.
    * A password changed in between yields a token bound to the new hash: still
      valid, and nothing issued for the old one is ever sent.

    A second delivery of the same job sends a second, equally valid mail.
    """
    asked = datetime.fromisoformat(requested_at)
    age = (datetime.now(UTC) - asked).total_seconds()
    if age > settings.mail_max_age_seconds:
        logger.warning(
            "Password reset mail for user %s dropped: requested %d minutes ago", user_id, age // 60
        )
        return

    sender = get_mail_sender()
    if sender is None:
        # The API does not queue without mail settings, so this is a worker
        # configured differently from the API. Retrying will not fix that.
        raise MailNotConfiguredError(
            "mail is not configured in the worker; set "
            + ", ".join(settings.missing_mail_settings())
        )

    async with _session_factory() as session:
        user = await session.get(User, UUID(user_id))
        if user is None or not user.is_active:
            logger.info("Password reset mail for user %s dropped: no such active account", user_id)
            return
        manager = UserManager(SQLAlchemyUserDatabase(session, User), sender)
        mail = reset_mail(user.email, user.name, manager.password_token(user))

    await sender.send(mail)
    logger.info("Password reset mail sent to user %s", user_id)
