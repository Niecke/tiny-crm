"""A stdio MCP server over tinyCRM's read-only agent API (#320).

Configured by two environment variables:

  TINYCRM_URL        the API base, as the frontend uses it: `https://crm.example.com/api`
                     (the ingress strips `/api`), or `http://localhost:8000` against a
                     local uvicorn
  TINYCRM_API_TOKEN  a `tc_live_…` token from Account → API tokens

Each tool is one GET on `/v1/agent/*` and returns the JSON body as is: the
endpoints are already compact. Failures are raised, so the MCP client sees a
tool error it can show the model.
"""

import os
import sys
from typing import Any

import httpx2
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TOKEN_PREFIX = "tc_live_"

server = MCPServer("tinycrm")

_client: httpx2.AsyncClient | None = None


class TinyCrmError(ToolError):
    """A request tinyCRM refused or could not answer.

    A ToolError, not a plain exception: the SDK passes its message to the client
    and hides everyone else's, and this message is for the model to act on.
    """


def configure(url: str, token: str, transport: httpx2.AsyncBaseTransport | None = None) -> None:
    """Point the tools at a tinyCRM. `transport` is for tests."""
    global _client
    _client = httpx2.AsyncClient(
        base_url=url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
        transport=transport,
    )


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if _client is None:
        raise TinyCrmError("tinycrm-mcp is not configured")
    try:
        response = await _client.get(f"/v1/agent{path}", params=params)
    except httpx2.HTTPError as exc:
        raise TinyCrmError(f"could not reach tinyCRM: {type(exc).__name__}") from exc
    if response.status_code == 401:
        raise TinyCrmError("token invalid or revoked")
    if response.status_code == 404:
        raise TinyCrmError("not found")
    if response.is_error:
        raise TinyCrmError(f"tinyCRM answered {response.status_code}: {_detail(response)}")
    body: dict[str, Any] = response.json()
    return body


def _detail(response: httpx2.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return response.reason_phrase
    return str(detail) if detail is not None else response.reason_phrase


@server.tool()
async def tinycrm_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Find contacts, organizations and open deals matching every word of `query`.

    Returns `{q, hits: [{type, id, title, subtitle?}]}` where type is `contact`,
    `organization` or `deal`. Use the id with tinycrm_get_contact or
    tinycrm_get_organization. `limit` is the most hits per type (1-20, default 5).
    """
    return await _get("/search", {"q": query, "limit": limit})


@server.tool()
async def tinycrm_get_contact(contact_id: str) -> dict[str, Any]:
    """A contact's profile (job title, organization, email, phone, tags, notes) and
    their five most recent interactions. `contact_id` is an id from tinycrm_search."""
    return await _get(f"/contacts/{contact_id}")


@server.tool()
async def tinycrm_get_organization(organization_id: str) -> dict[str, Any]:
    """An organization with its contacts, open deals and five most recent interactions.
    `organization_id` is an id from tinycrm_search."""
    return await _get(f"/organizations/{organization_id}")


@server.tool()
async def tinycrm_get_pipeline() -> dict[str, Any]:
    """The open pipeline: every deal still being prepared or competed for, in stage
    order, with `days_in_stage` and `totals` of expected value per currency."""
    return await _get("/deals/open")


@server.tool()
async def tinycrm_get_today_tasks() -> dict[str, Any]:
    """Open tasks that are overdue and those due today, in the operator's timezone."""
    return await _get("/tasks/today")


def main() -> None:
    url = os.environ.get("TINYCRM_URL", "").strip()
    token = os.environ.get("TINYCRM_API_TOKEN", "").strip()
    if not url:
        sys.exit("tinycrm-mcp: TINYCRM_URL is not set (e.g. https://crm.example.com/api)")
    if not token.startswith(TOKEN_PREFIX):
        sys.exit(f"tinycrm-mcp: TINYCRM_API_TOKEN must be set to a token starting {TOKEN_PREFIX}")
    configure(url, token)
    # stdio: the client launches this as a subprocess. Nothing but the protocol
    # may be written to stdout.
    server.run("stdio")


if __name__ == "__main__":
    main()
