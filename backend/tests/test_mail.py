"""The Brevo sender, against a mocked transport — no test talks to Brevo."""

import json

import httpx2
import pytest

from app.config import settings
from app.mail import (
    BREVO_SEND_URL,
    BrevoSender,
    Mail,
    MailDeliveryError,
    PermanentMailError,
    TransientMailError,
    get_mail_sender,
    invite_mail,
)

MAIL = Mail(
    to_address="alice@example.com",
    to_name="Alice",
    subject="Reset your tinyCRM password",
    text="token-bearing text",
    html="<p>token-bearing html</p>",
)


def _sender(handler: httpx2.MockTransport) -> BrevoSender:
    return BrevoSender("xkeysib-secret", "crm@example.com", "tinyCRM", transport=handler)


async def test_a_mail_becomes_one_brevo_request() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(201, json={"messageId": "<1@smtp-relay.brevo.com>"})

    await _sender(httpx2.MockTransport(handler)).send(MAIL)

    [request] = requests
    assert str(request.url) == BREVO_SEND_URL
    assert request.headers["api-key"] == "xkeysib-secret"
    assert json.loads(request.content) == {
        "sender": {"email": "crm@example.com", "name": "tinyCRM"},
        "to": [{"email": "alice@example.com", "name": "Alice"}],
        "subject": "Reset your tinyCRM password",
        "textContent": "token-bearing text",
        "htmlContent": "<p>token-bearing html</p>",
    }


async def test_a_refusal_raises_without_the_key_or_the_body() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"code": "unauthorized", "message": "Key not found"})

    # Permanent: the worker must not retry a key Brevo does not know.
    with pytest.raises(PermanentMailError) as raised:
        await _sender(httpx2.MockTransport(handler)).send(MAIL)

    assert "401" in str(raised.value)
    assert "xkeysib-secret" not in str(raised.value)
    assert "token-bearing" not in str(raised.value)


async def test_an_unreachable_brevo_raises() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(TransientMailError, match="could not reach Brevo"):
        await _sender(httpx2.MockTransport(handler)).send(MAIL)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        # Brevo's own trouble, or its rate limit: later may work.
        (500, TransientMailError),
        (503, TransientMailError),
        (429, TransientMailError),
        # About this request: asking again changes nothing.
        (400, PermanentMailError),
        (401, PermanentMailError),
        (403, PermanentMailError),
        # Not the 201 a sent mail gets, and nothing a retry would turn into one.
        (200, PermanentMailError),
    ],
)
async def test_the_status_decides_whether_a_retry_can_help(
    status: int, error: type[MailDeliveryError]
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"code": "x", "message": "y"})

    with pytest.raises(MailDeliveryError) as raised:
        await _sender(httpx2.MockTransport(handler)).send(MAIL)

    assert type(raised.value) is error


def test_the_html_escapes_the_name_and_the_text_does_not() -> None:
    mail = invite_mail("alice@example.com", "Alice <Admin>", "tok.en")

    assert mail.subject == "Your tinyCRM account"
    assert mail.text.startswith("Hello Alice <Admin>,\n\n")
    assert "Hello Alice &lt;Admin&gt;," in mail.html
    assert "<Admin>" not in mail.html
    assert mail.html.count('href="https://crm.example.com/reset-password#token=tok.en"') == 2


def test_no_sender_without_the_api_key() -> None:
    assert settings.missing_mail_settings() == ["BREVO_API_KEY"]
    assert get_mail_sender() is None


def test_a_sender_once_everything_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-secret")

    assert isinstance(get_mail_sender(), BrevoSender)
