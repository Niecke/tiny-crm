"""One access line per request, written by the app rather than by uvicorn.

uvicorn's access logger is handed five values (client address, method, path,
HTTP version, status) and neither times the request nor sees its headers, so
the duration and the user agent cannot be added there. This middleware logs the
same fields plus those two, and uvicorn's own line is switched off: the server
runs with `--no-access-log`, and log_config.json gives `uvicorn.access` no
handler. The second matters more — uvicorn decides per connection by asking the
logger whether it has handlers, and configure_logging() re-applies the config
after uvicorn has acted on the flag.

A pure ASGI middleware rather than `app.middleware("http")`, because it has to
  * be the outermost layer, so CORS and the login throttle are part of the time,
  * see the status of a streamed response (document downloads) and time it
    until its last chunk is sent, and
  * still log a request whose handler raised, with status 500.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.access")

# The header is whatever the client sends. JSON escaping already keeps it on one
# line; this keeps one request from writing an arbitrarily long one.
MAX_USER_AGENT_LENGTH = 512


def _user_agent(scope: Scope) -> str | None:
    user_agent = Headers(scope=scope).get("user-agent")
    return user_agent[:MAX_USER_AGENT_LENGTH] if user_agent is not None else None


def access_fields(scope: Scope, status: int, duration_ms: float) -> dict[str, Any]:
    """The access line's fields for one finished request."""
    fields: dict[str, Any] = {}
    # uvicorn's ProxyHeadersMiddleware wraps the app and has already put the
    # real client behind a trusted proxy here, so this is the address the login
    # throttle sees (_client_ip in ratelimit.py). None for a unix socket.
    client = scope.get("client")
    if client:
        host, port = client
        fields["source_ip"] = host
        # X-Forwarded-For names a host and no port, so for a proxied request
        # uvicorn reports port 0. That is every request in the cluster.
        if port:
            fields["source_port"] = port
    fields["http_method"] = scope["method"]
    # Quoted the way uvicorn's access line quoted it.
    fields["http_path"] = urllib.parse.quote(scope["path"])
    query = scope.get("query_string", b"")
    if query:
        fields["http_query"] = query.decode("latin-1")
    fields["http_version"] = scope.get("http_version", "1.1")
    fields["http_status"] = status
    fields["http_duration_ms"] = round(duration_ms, 2)
    user_agent = _user_agent(scope)
    if user_agent is not None:
        fields["http_user_agent"] = user_agent
    return fields


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        # Stays None if the app raises before it answers; Starlette's
        # ServerErrorMiddleware, outside this one, then sends a 500.
        status: int | None = None

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # The app returns once the last body chunk is sent, streamed or not.
            fields = access_fields(
                scope,
                status if status is not None else 500,
                (time.perf_counter() - start) * 1000,
            )
            logger.info(
                "%s %s %d",
                fields["http_method"],
                fields["http_path"],
                fields["http_status"],
                extra={"fields": fields},
            )
