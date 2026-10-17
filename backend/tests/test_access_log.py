"""The access line the app writes for every request (app/access_log.py).

Most tests run a small app behind the middleware, so they need no database; the
last ones check that the real app is wrapped and that uvicorn's line stays off.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from httpx2 import ASGITransport, AsyncClient
from starlette.types import ASGIApp, Message
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import access_log
from app.access_log import AccessLogMiddleware
from app.logging_config import JsonFormatter, configure_logging
from app.main import app as main_app
from app.ratelimit import _client_ip


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/client-ip")
    async def client_ip(request: Request) -> dict[str, str]:
        return {"ip": _client_ip(request)}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            for _ in range(2):
                await asyncio.sleep(0.03)
                yield b"chunk"

        return StreamingResponse(chunks(), media_type="application/octet-stream")

    app.add_middleware(AccessLogMiddleware)
    return app


def _client(app: ASGIApp, client: tuple[str, int] = ("10.42.0.1", 38084)) -> AsyncClient:
    # raise_app_exceptions=False: a handler that raises is answered with a 500,
    # the way uvicorn answers it, instead of the error surfacing in the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False, client=client)
    return AsyncClient(transport=transport, base_url="http://test")


def _access_lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    """The captured access records, rendered the way they reach stdout."""
    formatter = JsonFormatter()
    return [json.loads(formatter.format(r)) for r in caplog.records if r.name == "app.access"]


async def test_a_request_is_logged_once_with_its_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    async with _client(_make_app()) as client:
        response = await client.get("/ok?search=acme", headers={"User-Agent": "kube-probe/1.33"})
    assert response.status_code == 200

    [line] = _access_lines(caplog)
    assert line["logger"] == "app.access"
    assert line["log_level"] == "INFO"
    assert line["message"] == "GET /ok 200"
    assert line["source_ip"] == "10.42.0.1"
    assert line["source_port"] == 38084
    assert line["http_method"] == "GET"
    assert line["http_path"] == "/ok"
    assert line["http_query"] == "search=acme"
    assert line["http_version"] == "1.1"
    assert line["http_status"] == 200
    assert line["http_user_agent"] == "kube-probe/1.33"
    assert isinstance(line["http_duration_ms"], float)
    assert line["http_duration_ms"] >= 0


async def test_a_request_without_a_query_has_no_query_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    async with _client(_make_app()) as client:
        await client.get("/ok")

    [line] = _access_lines(caplog)
    assert "http_query" not in line


async def test_a_request_without_a_user_agent_has_no_user_agent_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    async with _client(_make_app()) as client:
        # httpx2 sends a User-Agent of its own unless told not to.
        del client.headers["User-Agent"]
        await client.get("/ok")

    [line] = _access_lines(caplog)
    assert "http_user_agent" not in line
    assert line["http_status"] == 200


async def test_a_long_user_agent_is_cut(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    async with _client(_make_app()) as client:
        await client.get("/ok", headers={"User-Agent": "x" * 10_000})

    [line] = _access_lines(caplog)
    assert line["http_user_agent"] == "x" * access_log.MAX_USER_AGENT_LENGTH


async def test_a_request_that_raises_is_logged_as_500(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    async with _client(_make_app()) as client:
        response = await client.get("/boom")
    assert response.status_code == 500

    [line] = _access_lines(caplog)
    assert line["message"] == "GET /boom 500"
    assert line["http_status"] == 500
    assert "http_duration_ms" in line


async def test_a_streamed_response_is_timed_until_its_last_chunk(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    async with _client(_make_app()) as client:
        response = await client.get("/stream")
    assert response.content == b"chunkchunk"

    [line] = _access_lines(caplog)
    assert line["http_status"] == 200
    # Two chunks, 30 ms apart from the start: the body took at least 60 ms.
    assert line["http_duration_ms"] >= 60


async def test_the_source_is_the_client_the_login_throttle_sees(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Behind the ingress: uvicorn's ProxyHeadersMiddleware wraps the app and
    replaces the proxy's address with the one in X-Forwarded-For."""
    caplog.set_level(logging.INFO, logger="app.access")
    # uvicorn and Starlette each type the ASGI interface their own way.
    proxied: Any = ProxyHeadersMiddleware(cast(Any, _make_app()), trusted_hosts="10.42.0.0/16")
    async with _client(proxied) as client:
        response = await client.get("/client-ip", headers={"X-Forwarded-For": "203.0.113.7"})

    [line] = _access_lines(caplog)
    assert line["source_ip"] == response.json()["ip"] == "203.0.113.7"
    # X-Forwarded-For carries no port.
    assert "source_port" not in line


async def test_a_request_without_a_peer_address_has_no_source_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A unix socket gives the scope no client."""
    caplog.set_level(logging.INFO, logger="app.access")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/ok",
        "raw_path": b"/ok",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "client": None,
        "server": None,
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await _make_app()(scope, receive, send)

    assert sent[0]["status"] == 200
    [line] = _access_lines(caplog)
    assert "source_ip" not in line
    assert "source_port" not in line
    assert line["http_path"] == "/ok"


def test_the_access_log_is_the_outermost_layer_of_the_app() -> None:
    """Outside CORS and the login throttle, so their time is part of the line."""
    assert cast(object, main_app.user_middleware[0].cls) is AccessLogMiddleware


async def test_the_app_logs_each_request_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    async with _client(main_app) as client:
        response = await client.get("/version")
    assert response.status_code == 200

    lines = _access_lines(caplog)
    assert [line["message"] for line in lines] == ["GET /version 200"]
    assert not [r for r in caplog.records if r.name == "uvicorn.access"]


def test_uvicorn_writes_no_access_line_of_its_own() -> None:
    """uvicorn logs a request only if its access logger has a handler, and asks
    per connection — after configure_logging() has re-applied log_config.json in
    the worker. So the config itself has to leave that logger without one."""
    configure_logging()

    assert not logging.getLogger("uvicorn.access").hasHandlers()
