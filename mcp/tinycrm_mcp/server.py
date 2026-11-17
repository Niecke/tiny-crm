"""A stdio MCP server over tinyCRM's agent API: read, plus proposals (#320, #321).

Configured by two environment variables:

  TINYCRM_URL        the API base, as the frontend uses it: `https://crm.example.com/api`
                     (the ingress strips `/api`), or `http://localhost:8000` against a
                     local uvicorn
  TINYCRM_API_TOKEN  a `tc_live_…` token from Account → API tokens

Each read tool is one GET on `/v1/agent/*` and returns the JSON body as is: the
endpoints are already compact. Each `tinycrm_propose_*` tool is one POST to
`/v1/agent/proposals`: it stages a change that waits for the operator to approve
it in tinyCRM → Approvals, and writes nothing to the CRM itself. Failures are
raised, so the MCP client sees a tool error it can show the model.
"""

import os
import sys
from typing import Any
from urllib.parse import quote

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
    try:
        body: dict[str, Any] = response.json()
    except ValueError as exc:
        raise TinyCrmError("tinyCRM did not return JSON — check TINYCRM_URL") from exc
    return body


PROPOSAL_HINT = "pending until the operator approves it in tinyCRM → Approvals"


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    if _client is None:
        raise TinyCrmError("tinycrm-mcp is not configured")
    try:
        response = await _client.post(f"/v1/agent{path}", json=body)
    except httpx2.HTTPError as exc:
        raise TinyCrmError(f"could not reach tinyCRM: {type(exc).__name__}") from exc
    if response.status_code == 401:
        raise TinyCrmError("token invalid or revoked")
    if response.status_code == 403:
        raise TinyCrmError(
            "this token may not propose changes — create one with 'Allow proposing changes'"
        )
    if response.status_code == 404:
        raise TinyCrmError("not found")
    if response.status_code == 422:
        raise TinyCrmError(f"invalid proposal: {_detail(response)}")
    if response.is_error:
        raise TinyCrmError(f"tinyCRM answered {response.status_code}: {_detail(response)}")
    try:
        answer: dict[str, Any] = response.json()
    except ValueError as exc:
        raise TinyCrmError("tinyCRM did not return JSON — check TINYCRM_URL") from exc
    return answer


def _given(**fields: Any) -> dict[str, Any]:
    """The arguments that were actually passed: None means "not sent"."""
    return {key: value for key, value in fields.items() if value is not None}


async def _propose(
    entity_type: str,
    action: str,
    payload: dict[str, Any],
    reason: str,
    target_id: str | None = None,
) -> dict[str, Any]:
    body = _given(
        entity_type=entity_type,
        action=action,
        target_id=target_id,
        payload=payload,
        reason=reason,
    )
    answer = await _post("/proposals", body)
    return {"id": answer.get("id"), "status": answer.get("status"), "hint": PROPOSAL_HINT}


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
    return await _get(f"/contacts/{quote(contact_id, safe='')}")


@server.tool()
async def tinycrm_get_organization(organization_id: str) -> dict[str, Any]:
    """An organization with its contacts, open deals and five most recent interactions.
    `organization_id` is an id from tinycrm_search."""
    return await _get(f"/organizations/{quote(organization_id, safe='')}")


@server.tool()
async def tinycrm_get_pipeline() -> dict[str, Any]:
    """The open pipeline: every deal still being prepared or competed for, in stage
    order, with `days_in_stage` and `totals` of expected value per currency."""
    return await _get("/deals/open")


@server.tool()
async def tinycrm_get_today_tasks() -> dict[str, Any]:
    """Open tasks that are overdue and those due today, in the operator's timezone."""
    return await _get("/tasks/today")


@server.tool()
async def tinycrm_propose_contact_creation(
    name: str,
    reason: str,
    job_title: str | None = None,
    organization_id: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    city: str | None = None,
    country: str | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Propose a new contact. Nothing is created until the operator approves it.

    `reason` is why — shown to the operator next to the proposal (e.g. "Met at the
    Vienna meetup, asked for an intro"). `organization_id` is an id from
    tinycrm_search; `country` is a two-letter code. Returns `{id, status, hint}`.
    """
    payload = _given(
        name=name,
        job_title=job_title,
        organization_id=organization_id,
        email=email,
        phone=phone,
        city=city,
        country=country,
        tags=tags,
        notes=notes,
    )
    return await _propose("contact", "create", payload, reason)


@server.tool()
async def tinycrm_propose_contact_update(
    contact_id: str, changes: dict[str, Any], reason: str
) -> dict[str, Any]:
    """Propose changes to a contact. Nothing changes until the operator approves.

    `changes` holds only the fields to change, under the contact's field names:
    name, job_title, organization_id, email, phone, city, country, tags, notes.
    `contact_id` is an id from tinycrm_search. `reason` is why. Returns
    `{id, status, hint}`.
    """
    return await _propose("contact", "update", changes, reason, target_id=contact_id)


@server.tool()
async def tinycrm_propose_deal_update(
    deal_id: str, changes: dict[str, Any], reason: str
) -> dict[str, Any]:
    """Propose changes to a deal. Nothing changes until the operator approves.

    `changes` holds only the fields to change, under the deal's field names:
    title, stage (draft, lead, qualified, proposal, negotiation, won, running,
    completed, lost), lost_reason, probability, expected_close_date, notes. `deal_id` is an id from
    tinycrm_search or tinycrm_get_pipeline. `reason` is why. Returns
    `{id, status, hint}`.
    """
    return await _propose("deal", "update", changes, reason, target_id=deal_id)


@server.tool()
async def tinycrm_propose_task_creation(
    title: str,
    reason: str,
    due_date: str | None = None,
    priority: int | None = None,
    contact_id: str | None = None,
    deal_id: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Propose a new task. Nothing is created until the operator approves it.

    `due_date` is ISO 8601 (`2026-12-01`); `priority` an integer; `contact_id` and
    `deal_id` ids from tinycrm_search. `reason` is why. Returns `{id, status, hint}`.
    """
    payload = _given(
        title=title,
        due_date=due_date,
        priority=priority,
        contact_id=contact_id,
        deal_id=deal_id,
        description=description,
    )
    return await _propose("task", "create", payload, reason)


@server.tool()
async def tinycrm_propose_interaction_log(
    subject: str,
    occurred_at: str,
    reason: str,
    kind: str = "note",
    notes: str | None = None,
    contact_ids: list[str] | None = None,
    organization_ids: list[str] | None = None,
    deal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Propose logging an interaction (a call, meeting, email, note…). Nothing is
    logged until the operator approves it.

    `kind` is one of call, meeting, event, email, note, other. `occurred_at` is an
    ISO 8601 timestamp with a timezone (`2026-11-10T10:00:00Z`). The id lists come
    from tinycrm_search. `reason` is why. Returns `{id, status, hint}`.
    """
    payload = _given(
        subject=subject,
        occurred_at=occurred_at,
        kind=kind,
        notes=notes,
        contact_ids=contact_ids,
        organization_ids=organization_ids,
        deal_ids=deal_ids,
    )
    return await _propose("interaction", "create", payload, reason)


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
