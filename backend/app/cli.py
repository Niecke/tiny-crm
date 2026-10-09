"""Operator commands. There is no signup route; accounts come from here.

    python -m app.cli create-user you@example.com --name "You"
    python -m app.cli create-user you@example.com --set-password   # no mail
    printf '%s\n' "$PW" | python -m app.cli create-user you@example.com --set-password
    python -m app.cli invite you@example.com                       # send again
    python -m app.cli unlock you@example.com                       # end a login lock
    python -m app.cli disable-mfa you@example.com                  # lost authenticator
    python -m app.cli ping-worker                                  # is the worker running?

Run from the backend directory (/app in the image), so `app` is importable.
Reads the same environment as the API: DATABASE_URL, and for mail
BREVO_API_KEY, MAIL_FROM_ADDRESS and APP_URL.

Accounts go through UserManager rather than straight into the table, so the
password rule applies and the invite is the same token the reset flow redeems.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import typer
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException, UserAlreadyExists
from procrastinate.jobs import Status
from pydantic import ValidationError

# The whole model registry, not just User: SQLAlchemy configures mappers against
# all of it on first query, and a relationship naming an unimported model fails.
import app.models  # noqa: F401
from app.auth import mfa
from app.auth.throttle import clear_login, clear_reset_mail
from app.auth.users import User, UserManager
from app.config import settings
from app.db import _session_factory
from app.jobs import jobs_app, ping
from app.logging_config import configure_logging
from app.mail import MailDeliveryError, get_mail_sender
from app.schemas.user import UserCreate

cli = typer.Typer(no_args_is_help=True, add_completion=False, help="tinyCRM operator commands.")


def _fail(message: str) -> typer.Exit:
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(code=1)


@asynccontextmanager
async def _user_manager() -> AsyncIterator[UserManager]:
    async with _session_factory() as session:
        yield UserManager(SQLAlchemyUserDatabase(session, User), get_mail_sender())


async def _create_user(email: str, name: str | None, superuser: bool, password: str | None) -> None:
    async with _user_manager() as manager:
        if password is None and manager.mail_sender is None:
            # Checked before creating anything: an account nobody can sign in
            # to is worse than no account.
            missing = ", ".join(settings.missing_mail_settings())
            raise _fail(f"mail is not configured ({missing}); set it or use --set-password")
        try:
            user_create = UserCreate(
                email=email,
                # Invited accounts get a password nobody knows; the invite
                # link replaces it.
                password=password or secrets.token_urlsafe(32),
                name=name,
                is_superuser=superuser,
            )
        except ValidationError as exc:
            raise _fail(f"invalid input: {exc.errors()[0]['msg']}") from None
        try:
            user = await manager.create(user_create)
        except UserAlreadyExists:
            raise _fail(f"a user with the address {email} already exists") from None
        except InvalidPasswordException as exc:
            raise _fail(str(exc.reason)) from None
        typer.echo(f"Created user {user.email} ({user.id}).")

        if password is not None:
            return
        try:
            await manager.send_invite(user)
        except MailDeliveryError as exc:
            raise _fail(
                f"the account exists, but the invite was not sent: {exc}\n"
                f"Retry with: python -m app.cli invite {email}"
            ) from None
        typer.echo(f"Invite sent to {user.email}.")


async def _invite(email: str) -> None:
    async with _user_manager() as manager:
        user = await manager.user_db.get_by_email(email)
        if user is None:
            raise _fail(f"no user with the address {email}")
        if not user.is_active:
            raise _fail(f"{email} is deactivated")
        try:
            await manager.send_invite(user)
        except MailDeliveryError as exc:
            raise _fail(f"invite not sent: {exc}") from None
        typer.echo(f"Invite sent to {user.email}.")


async def _unlock(email: str) -> None:
    async with _session_factory() as session:
        login = await clear_login(session, email)
        reset_mail = await clear_reset_mail(session, email)
    if login or reset_mail:
        typer.echo(f"Cleared the login backoff and reset-mail cooldown of {email}.")
    else:
        typer.echo(f"Nothing to clear for {email}.")


async def _disable_mfa(email: str) -> None:
    async with _user_manager() as manager:
        user = await manager.user_db.get_by_email(email)
        if user is None:
            raise _fail(f"no user with the address {email}")
        if await mfa.disable(manager.db, user.id):
            typer.echo(f"Two-factor sign-in turned off for {user.email}.")
        else:
            typer.echo(f"{user.email} has no two-factor sign-in to turn off.")


async def _ping_worker(queues: list[str], timeout: float) -> None:
    async with jobs_app.open_async():
        started = time.monotonic()
        waiting = {
            queue: await ping.configure(queue=queue).defer_async()
            for queue in dict.fromkeys(queues)
        }
        while waiting:
            for queue, job_id in list(waiting.items()):
                status = await jobs_app.job_manager.get_job_status_async(job_id)
                if status is Status.SUCCEEDED:
                    del waiting[queue]
                    typer.echo(f"{queue}: answered after {time.monotonic() - started:.1f}s.")
                elif status not in (Status.TODO, Status.DOING):
                    raise _fail(f"{queue}: the ping job ended as {status.value}")
            if waiting and time.monotonic() - started > timeout:
                # The jobs stay queued and run when a worker comes up; they
                # do nothing, so there is no reason to cancel them.
                raise _fail(
                    f"no worker took a job from {', '.join(waiting)} within {timeout:g}s — "
                    "is `python -m app.worker` running, and does WORKER_POOLS list the queue?"
                )
            await asyncio.sleep(0.2)


@cli.command("create-user")
def create_user(
    email: str,
    name: Annotated[
        str | None, typer.Option(help="Display name, used in the mail greeting.")
    ] = None,
    superuser: Annotated[bool, typer.Option(help="Mark the account as superuser.")] = False,
    set_password: Annotated[
        bool,
        typer.Option(
            "--set-password",
            help="Set the password instead of mailing an invite: prompted for on a "
            "terminal, read as one line from stdin otherwise. For a first account "
            "before mail is set up, local development and ci/smoke.sh.",
        ),
    ] = False,
) -> None:
    """Create an account and mail it a link to choose its password."""
    password: str | None = None
    if set_password:
        if sys.stdin.isatty():
            password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
        else:
            # Never an argument: argv shows up in `ps` and in shell history.
            password = sys.stdin.readline().rstrip("\r\n")
    asyncio.run(_create_user(email, name, superuser, password))


@cli.command()
def invite(email: str) -> None:
    """Mail an existing account a fresh set-your-password link.

    For an invite that expired or never arrived. Links sent earlier stay valid
    until they expire or one of them is used.
    """
    asyncio.run(_invite(email))


@cli.command()
def unlock(email: str) -> None:
    """End the failed-login backoff and the reset-mail cooldown of an address.

    For an operator locked out of their own account by someone guessing at it.
    The address need not have an account: failures are counted per address.
    """
    asyncio.run(_unlock(email))


@cli.command("disable-mfa")
def disable_mfa(email: str) -> None:
    """Turn off two-factor sign-in for an account, dropping its recovery codes.

    For someone who lost both the authenticator and the recovery codes. Their
    password still applies; they can set MFA up again from the account page.
    """
    asyncio.run(_disable_mfa(email))


@cli.command("ping-worker")
def ping_worker(
    queue: Annotated[
        list[str] | None,
        typer.Option(help="Queue to ping; repeat for several. Default: every queue in a pool."),
    ] = None,
    timeout: Annotated[float, typer.Option(help="Seconds to wait for the answers.")] = 30,
) -> None:
    """Check that the background worker is taking jobs.

    Queues a job that does nothing on each queue and waits for it to be done:
    proof of the queue's schema, of a running worker and of a pool serving that
    queue. An answer well under five seconds also means the worker heard about
    the job (LISTEN/NOTIFY) instead of finding it on its next poll.

    The queues come from this process's WORKER_POOLS, which is the worker's
    only if both read the same environment — name them with --queue otherwise.
    """
    queues = queue or [name for pool in settings.worker_pools for name in pool.queues]
    asyncio.run(_ping_worker(queues, timeout))


if __name__ == "__main__":
    configure_logging()
    cli()
