"""The tools against a mock tinyCRM, called directly and through an in-process MCP client."""

import json
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest
from mcp import Client

from tinycrm_mcp import server
from tinycrm_mcp.server import TinyCrmError, main

TOKEN = "tc_live_secret"


class Mock:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.status = 200
        self.body: Any = {"ok": True}

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(self.status, json=self.body)


@pytest.fixture
def mock() -> Iterator[Mock]:
    mock = Mock()
    server.configure("https://crm.test/api/", TOKEN, httpx2.MockTransport(mock))
    yield mock
    server._client = None


async def test_search_sends_the_query_with_the_token(mock: Mock) -> None:
    mock.body = {"q": "acme", "hits": []}

    assert await server.tinycrm_search("acme", limit=3) == {"q": "acme", "hits": []}

    [request] = mock.requests
    assert request.method == "GET"
    assert request.url.path == "/api/v1/agent/search"
    assert dict(request.url.params) == {"q": "acme", "limit": "3"}
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize(
    ("call", "path"),
    [
        (lambda: server.tinycrm_get_contact("c1"), "/api/v1/agent/contacts/c1"),
        (lambda: server.tinycrm_get_organization("o1"), "/api/v1/agent/organizations/o1"),
        (lambda: server.tinycrm_get_pipeline(), "/api/v1/agent/deals/open"),
        (lambda: server.tinycrm_get_today_tasks(), "/api/v1/agent/tasks/today"),
    ],
)
async def test_each_tool_reads_its_endpoint(mock: Mock, call: Any, path: str) -> None:
    assert await call() == {"ok": True}
    assert [r.url.path for r in mock.requests] == [path]
    assert mock.requests[0].headers["authorization"] == f"Bearer {TOKEN}"


async def test_a_401_says_the_token_is_bad(mock: Mock) -> None:
    mock.status = 401
    with pytest.raises(TinyCrmError, match="token invalid or revoked"):
        await server.tinycrm_get_pipeline()


async def test_a_404_says_not_found(mock: Mock) -> None:
    mock.status = 404
    with pytest.raises(TinyCrmError, match="not found"):
        await server.tinycrm_get_contact("nope")


async def test_other_errors_carry_status_and_detail(mock: Mock) -> None:
    mock.status = 422
    mock.body = {"detail": "Type at least 2 characters to search for"}
    with pytest.raises(TinyCrmError, match="422: Type at least 2 characters"):
        await server.tinycrm_search("a")


async def test_an_unreachable_server_is_a_tool_error() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    server.configure("https://crm.test", TOKEN, httpx2.MockTransport(refuse))
    try:
        with pytest.raises(TinyCrmError, match="could not reach tinyCRM: ConnectError"):
            await server.tinycrm_get_pipeline()
    finally:
        server._client = None


async def test_the_server_lists_the_five_tools(mock: Mock) -> None:
    async with Client(server.server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert set(tools) == {
        "tinycrm_search",
        "tinycrm_get_contact",
        "tinycrm_get_organization",
        "tinycrm_get_pipeline",
        "tinycrm_get_today_tasks",
    }
    assert tools["tinycrm_search"].input_schema["required"] == ["query"]
    assert all(t.description for t in tools.values())


async def test_a_tool_called_over_mcp_returns_the_body(mock: Mock) -> None:
    mock.body = {"deals": [], "totals": {}}
    async with Client(server.server) as client:
        result = await client.call_tool("tinycrm_get_pipeline", {})

    assert not result.is_error
    assert json.loads(result.content[0].text) == {"deals": [], "totals": {}}  # type: ignore[union-attr]


async def test_a_failure_over_mcp_is_a_tool_error(mock: Mock) -> None:
    mock.status = 401
    async with Client(server.server) as client:
        result = await client.call_tool("tinycrm_get_pipeline", {})

    assert result.is_error
    assert "token invalid or revoked" in result.content[0].text  # type: ignore[union-attr]


def test_main_needs_a_url_and_a_tc_live_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TINYCRM_URL", raising=False)
    monkeypatch.setenv("TINYCRM_API_TOKEN", TOKEN)
    with pytest.raises(SystemExit, match="TINYCRM_URL"):
        main()

    monkeypatch.setenv("TINYCRM_URL", "http://localhost:8000")
    monkeypatch.setenv("TINYCRM_API_TOKEN", "eyJ-a-session-jwt")
    with pytest.raises(SystemExit, match="tc_live_"):
        main()
