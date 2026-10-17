"""Unit tests for the JSON log formatter."""

import json
import logging
import sys
from typing import Any

from app.logging_config import JsonFormatter


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
    # What logger.info(..., extra={...}) does with its extra.
    for key, value in kwargs.get("extra", {}).items():
        setattr(record, key, value)
    rendered: dict[str, Any] = json.loads(JsonFormatter().format(record))
    return rendered


def test_fields_passed_as_extra_become_keys_of_their_own() -> None:
    log = _render(
        "app.access",
        "%s %s %d",
        ("GET", "/version", 200),
        extra={"fields": {"http_method": "GET", "http_status": 200, "http_duration_ms": 1.5}},
    )

    assert log["message"] == "GET /version 200"
    assert log["http_method"] == "GET"
    assert log["http_status"] == 200
    assert log["http_duration_ms"] == 1.5
    assert "fields" not in log


def test_fields_cannot_replace_the_base_keys() -> None:
    log = _render(
        "app.access",
        "real message",
        (),
        extra={"fields": {"message": "forged", "logger": "x", "exception": "y", "ok": 1}},
    )

    assert log["message"] == "real message"
    assert log["logger"] == "app.access"
    assert "exception" not in log
    assert log["ok"] == 1


def test_other_loggers_keep_their_formatted_message() -> None:
    log = _render("app.mail", "Password reset mail to %s not sent: %s", ("a@example.com", "boom"))

    assert log["message"] == "Password reset mail to a@example.com not sent: boom"
    assert not [key for key in log if key.startswith(("http_", "source_"))]


def test_an_exception_is_still_attached() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        log = _render("app.main", "It broke", (), exc_info=sys.exc_info())

    assert log["message"] == "It broke"
    assert "ValueError: boom" in log["exception"]
