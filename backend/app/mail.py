"""Transactional mail: the invite a new account gets, and the password-reset link.

Sent through Brevo's HTTP API rather than SMTP — one POST, no connection to
keep, and Brevo handles SPF/DKIM for the verified sender domain. The briefing
shows the same shape for Slack (app/briefing.py), but a reset link has to reach
the person's own mailbox, so nothing is shared with it.

Both mails carry the same kind of token: a fastapi-users reset token (see
UserManager.password_token), redeemed at POST /auth/reset-password. An invite is
a reset for an account whose password nobody knows yet.

The copy lives in app/templates/mail/: a .txt and an .html per mail, the
subject set at the top of the .txt.

The token is a credential for the account until it is used or expires. It goes
into the mail body and nowhere else — never a log line, never an error message,
never a queued job.

Who sends: the invite goes out from the CLI, with the operator watching. The
reset link is queued by the API and sent by the worker (app/jobs/mail.py), so
that a request never waits for Brevo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

import httpx2
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"

# How long to wait for Brevo. Short enough that the operator at the CLI is not
# left staring at a stalled invite, and that a worker slot is not held by one;
# a queued mail is simply tried again.
BREVO_TIMEOUT_SECONDS = 10

# Where the links land: the frontend's page (src/routes/reset-password.tsx in
# frontend-next/). It posts the token with the new password to
# /auth/reset-password. Links sent while the page lived under /next still work:
# the frontend redirects that prefix to the root.
RESET_PATH = "/reset-password"

# One .txt and one .html per mail. StrictUndefined turns a misspelt variable
# into an error in the tests instead of a blank in someone's inbox.
_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates" / "mail"),
    autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=False),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class Mail:
    to_address: str
    to_name: str | None
    subject: str
    text: str
    html: str


class MailSender(Protocol):
    async def send(self, mail: Mail) -> None:
        """Deliver `mail` or raise MailDeliveryError."""


class MailDeliveryError(RuntimeError):
    """The provider did not accept the mail. The text never carries the API key
    or the mail body — the body holds the token, and this ends up in logs.

    Raised as one of the two below, which say whether trying again can help.
    The worker retries on one and gives up on the other (app/jobs/mail.py);
    the CLI reports either to the operator, who is the retry.
    """


class TransientMailError(MailDeliveryError):
    """Brevo could not be reached or was not able to answer: a network error, a
    5xx, a rate limit. The same request may well go through later."""


class PermanentMailError(MailDeliveryError):
    """Brevo understood the request and refused it — an unverified sender, a
    revoked key. Sending it again gets the same answer."""


class MailNotConfiguredError(PermanentMailError):
    """There is no sender, so nothing could be sent."""


class BrevoSender:
    def __init__(
        self,
        api_key: str,
        from_address: str,
        from_name: str,
        # Injected by the tests; production talks to the network.
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._from = {"email": from_address, "name": from_name}
        self._transport = transport

    async def send(self, mail: Mail) -> None:
        recipient = {"email": mail.to_address}
        if mail.to_name:
            recipient["name"] = mail.to_name
        payload = {
            "sender": self._from,
            "to": [recipient],
            "subject": mail.subject,
            "textContent": mail.text,
            "htmlContent": mail.html,
        }
        try:
            async with httpx2.AsyncClient(
                transport=self._transport, timeout=BREVO_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    BREVO_SEND_URL,
                    json=payload,
                    headers={"api-key": self._api_key, "accept": "application/json"},
                )
        except httpx2.HTTPError as exc:
            raise TransientMailError(f"could not reach Brevo: {type(exc).__name__}") from None

        # 201 with a messageId on success. Brevo's error body is a short
        # {"code", "message"} naming the problem (unverified sender, bad key)
        # without echoing the request.
        if response.status_code != 201:
            # A 5xx is Brevo's trouble and a 429 its rate limit; both pass.
            # Any other answer is about this request and will not change.
            transient = response.status_code == 429 or response.status_code >= 500
            error = TransientMailError if transient else PermanentMailError
            raise error(
                f"Brevo refused the mail: HTTP {response.status_code} {response.text.strip()}"
            )
        logger.info("Mail %r accepted by Brevo: %s", mail.subject, response.text.strip())


def get_mail_sender() -> MailSender | None:
    """The configured sender, or None when mail is not set up.

    A FastAPI dependency (through get_user_manager), so the tests swap in an
    outbox with app.dependency_overrides.
    """
    if settings.missing_mail_settings():
        return None
    assert settings.brevo_api_key is not None
    assert settings.mail_from_address is not None
    return BrevoSender(settings.brevo_api_key, settings.mail_from_address, settings.mail_from_name)


# --- Content -----------------------------------------------------------------


def password_link(token: str) -> str:
    assert settings.app_url is not None, "get_mail_sender() checks APP_URL"
    # In the fragment, not the query: a browser never sends the fragment, so the
    # token stays out of the ingress and Caddy access logs and out of Referer.
    return f"{settings.app_url.rstrip('/')}{RESET_PATH}#{urlencode({'token': token})}"


def _hours(seconds: int) -> str:
    hours = round(seconds / 3600)
    return "1 hour" if hours == 1 else f"{hours} hours"


def _render(template: str, to_address: str, to_name: str | None, token: str) -> Mail:
    """Render `<template>.txt` and `<template>.html` into one Mail.

    The subject lives in the .txt template as `{% set subject = ... %}`, next to
    the copy it belongs with; make_module() exposes it as an attribute. The HTML
    is autoescaped (the name is operator input), the text is not.
    """
    context = {
        "name": to_name,
        "link": password_link(token),
        "lifetime": _hours(settings.password_token_lifetime_seconds),
    }
    text = _templates.get_template(f"{template}.txt").make_module(context)
    # Template-defined names are dynamic attributes, invisible to mypy.
    subject = str(getattr(text, "subject"))  # noqa: B009
    markup = _templates.get_template(f"{template}.html").render(context, subject=subject)
    return Mail(to_address, to_name, subject, str(text), markup)


def invite_mail(to_address: str, to_name: str | None, token: str) -> Mail:
    return _render("invite", to_address, to_name, token)


def reset_mail(to_address: str, to_name: str | None, token: str) -> Mail:
    return _render("reset", to_address, to_name, token)
