"""Unit tests for the JSON log formatter.

Access records are built the way uvicorn builds them — its format string and
its five args — so these fail if the formatter stops understanding that call.
"""

import json
import logging
import sys
from typing import Any

from app.logging_config import JsonFormatter

# What every uvicorn HTTP implementation passes to access_logger.info().
_UVICORN_ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'


def _render(name: str, msg: str, args: tuple[object, ...], **kwargs: Any) -> dict[str, Any]:
    record = logging.LogRecord(
        name=name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=kwargs.get("exc_info"),
    )
    rendered: dict[str, Any] = json.loads(JsonFormatter().format(record))
    return rendered


def _access(client_addr: str, method: str, path: str, status: int) -> dict[str, Any]:
    return _render(
        "uvicorn.access", _UVICORN_ACCESS_FORMAT, (client_addr, method, path, "1.1", status)
    )


def test_an_access_record_carries_the_request_as_separate_fields() -> None:
    log = _access("10.42.0.1:38084", "GET", "/version", 200)

    assert log["logger"] == "uvicorn.access"
    assert log["log_level"] == "INFO"
    assert log["source_ip"] == "10.42.0.1"
    assert log["source_port"] == 38084
    assert log["http_method"] == "GET"
    assert log["http_path"] == "/version"
    assert log["http_version"] == "1.1"
    assert log["http_status"] == 200
    assert "http_query" not in log


def test_the_access_message_no_longer_repeats_the_client_address() -> None:
    log = _access("10.42.0.1:38084", "GET", "/version", 200)

    assert log["message"] == "GET /version 200"


def test_the_query_string_is_split_from_the_path() -> None:
    log = _access("10.42.0.1:38084", "GET", "/contacts/?search=acme&limit=50", 200)

    assert log["http_path"] == "/contacts/"
    assert log["http_query"] == "search=acme&limit=50"
    assert log["message"] == "GET /contacts/ 200"


def test_an_ipv6_client_is_split_on_the_last_colon() -> None:
    log = _access("2001:db8::1:54321", "POST", "/auth/jwt/login", 400)

    assert log["source_ip"] == "2001:db8::1"
    assert log["source_port"] == 54321
    assert log["http_status"] == 400


def test_a_proxied_request_has_an_address_but_no_port() -> None:
    """uvicorn takes the host from X-Forwarded-For and fills in port 0."""
    log = _access("203.0.113.7:0", "GET", "/contacts/", 200)

    assert log["source_ip"] == "203.0.113.7"
    assert "source_port" not in log


def test_a_request_without_a_peer_address_has_no_source_fields() -> None:
    """uvicorn passes an empty string when the scope has no client."""
    log = _access("", "GET", "/health", 200)

    assert "source_ip" not in log
    assert "source_port" not in log
    assert log["http_path"] == "/health"


def test_other_loggers_keep_their_formatted_message() -> None:
    log = _render("app.mail", "Password reset mail to %s not sent: %s", ("a@example.com", "boom"))

    assert log["message"] == "Password reset mail to a@example.com not sent: boom"
    assert not [key for key in log if key.startswith(("http_", "source_"))]


def test_an_access_record_of_another_shape_is_rendered_flat() -> None:
    """A uvicorn that logs differently must still produce a readable line."""
    log = _render("uvicorn.access", "%s %s", ("GET", "/health"))

    assert log["message"] == "GET /health"
    assert not [key for key in log if key.startswith(("http_", "source_"))]

    # Five args as today, but the last one is no longer the numeric status.
    log = _render("uvicorn.access", "%s %s %s %s %s", ("a", "GET", "/health", "1.1", "OK"))

    assert log["message"] == "a GET /health 1.1 OK"
    assert not [key for key in log if key.startswith(("http_", "source_"))]


def test_an_exception_is_still_attached() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        log = _render("app.main", "It broke", (), exc_info=sys.exc_info())

    assert log["message"] == "It broke"
    assert "ValueError: boom" in log["exception"]
