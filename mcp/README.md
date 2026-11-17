# tinyCRM MCP server

A small [Model Context Protocol](https://modelcontextprotocol.io) server that lets
an agent (Claude Code, Cursor, Pi, …) read tinyCRM — search, a contact, an
organization, the open pipeline, today's tasks — and **propose** changes, which
wait for you to approve them. It is a thin wrapper over the agent API
(`/api/v1/agent/*`, see `FEATURES.md` → *Agent API*) and
speaks **stdio** — the client launches it as a subprocess. It is not part of the
backend image.

## Get a token

Account → **API tokens** → *Generate token*. The token (`tc_live_…`) is shown
once. Make one per tool so each can be revoked on its own. A token is read-only
by default and works on the agent API only.

To let the agent *propose* changes, tick **Allow proposing changes** when you
generate the token (the `propose` scope). A proposal never writes to your CRM: it
waits in **Approvals**, where you approve, edit or reject it. A read-only token
can use every tool except the `tinycrm_propose_*` ones.

## Configure

| Variable | Value |
| --- | --- |
| `TINYCRM_URL` | The API base, as the web app uses it: `https://crm.example.com/api` (the ingress strips `/api`), or `http://localhost:8000` against a local `uvicorn`. |
| `TINYCRM_API_TOKEN` | The `tc_live_…` token. The server refuses to start without it. |

Run it (needs [uv](https://docs.astral.sh/uv/)):

```bash
TINYCRM_URL=https://crm.example.com/api TINYCRM_API_TOKEN=tc_live_… \
  uv run --directory mcp tinycrm-mcp
```

### Claude Code

```bash
claude mcp add tinycrm \
  --env TINYCRM_URL=https://crm.example.com/api \
  --env TINYCRM_API_TOKEN=tc_live_… \
  -- uv run --directory /path/to/tiny-crm/mcp tinycrm-mcp
```

### Any client that takes an `mcpServers` block (Cursor, Pi, …)

```json
{
  "mcpServers": {
    "tinycrm": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/tiny-crm/mcp", "tinycrm-mcp"],
      "env": {
        "TINYCRM_URL": "https://crm.example.com/api",
        "TINYCRM_API_TOKEN": "tc_live_…"
      }
    }
  }
}
```

## Tools

The read tools are one `GET` each and return the endpoint's JSON as is. Nothing
that is null or empty is sent, to keep the answer small. The propose tools are
one `POST` each and need a token with the `propose` scope.

| Tool | Arguments | Endpoint |
| --- | --- | --- |
| `tinycrm_search` | `query` (string, ≥ 2 characters; every word must match), `limit` (int, 1–20, default 5, per type) | `GET /v1/agent/search?q=&limit=` |
| `tinycrm_get_contact` | `contact_id` (string, from search) | `GET /v1/agent/contacts/{id}` |
| `tinycrm_get_organization` | `organization_id` (string, from search) | `GET /v1/agent/organizations/{id}` |
| `tinycrm_get_pipeline` | none | `GET /v1/agent/deals/open` |
| `tinycrm_get_today_tasks` | none | `GET /v1/agent/tasks/today` |
| `tinycrm_propose_contact_creation` | `name`, `reason`; optional `job_title`, `organization_id`, `email`, `phone`, `city`, `country`, `tags`, `notes` | `POST /v1/agent/proposals` |
| `tinycrm_propose_contact_update` | `contact_id`, `changes` (object of contact fields), `reason` | `POST /v1/agent/proposals` |
| `tinycrm_propose_deal_update` | `deal_id`, `changes` (object of deal fields), `reason` | `POST /v1/agent/proposals` |
| `tinycrm_propose_task_creation` | `title`, `reason`; optional `due_date`, `priority`, `contact_id`, `deal_id`, `description` | `POST /v1/agent/proposals` |
| `tinycrm_propose_interaction_log` | `subject`, `occurred_at`, `reason`; optional `kind` (default `note`), `notes`, `contact_ids`, `organization_ids`, `deal_ids` | `POST /v1/agent/proposals` |

Search covers contacts, organizations and **open** deals (not won, lost or
archived ones).

### Example responses

`tinycrm_search("anna acme")`:

```json
{"q": "anna acme", "hits": [
  {"type": "contact", "id": "…", "title": "Anna Berger", "subtitle": "CTO · Acme GmbH"},
  {"type": "deal", "id": "…", "title": "Acme rollout", "subtitle": "Proposal · Acme GmbH"}
]}
```

`tinycrm_get_contact`:

```json
{"id": "…", "name": "Anna Berger", "job_title": "CTO",
 "organization": {"id": "…", "name": "Acme GmbH"}, "email": "anna@acme.test",
 "tags": ["vip"],
 "recent_interactions": [
   {"id": "…", "kind": "call", "subject": "Call about rollout",
    "occurred_at": "2026-11-03T09:00:00Z", "done": true,
    "notes_excerpt": "Wants a proposal by the end of the month…"}]}
```

`tinycrm_get_organization` — `{id, name, domain?, email?, phone?, industry?, notes?,
contacts?: [{id, name, job_title?}], open_deals?: [{id, title, stage}],
recent_interactions?: […]}`.

`tinycrm_get_pipeline`:

```json
{"deals": [
  {"id": "…", "title": "Acme rollout", "stage": "proposal", "currency": "EUR",
   "expected_value": "12000.00", "probability": 40, "days_in_stage": 3,
   "organization_name": "Acme GmbH"}],
 "totals": {"EUR": "12000.00"}}
```

`truncated: true` is added when there are more than 200 open deals; `totals`
always covers all of them.

`tinycrm_get_today_tasks`:

```json
{"date": "2026-11-11", "timezone": "Europe/Berlin",
 "overdue": [{"id": "…", "title": "Send offer", "priority": 2, "days_late": 2}],
 "today": [{"id": "…", "title": "Call Anna", "priority": 1, "contact_name": "Anna Berger"}]}
```

A propose tool returns `{id, status, hint}` — the proposal is `pending` until you
approve it in tinyCRM → **Approvals**:

```json
{"id": "…", "status": "pending",
 "hint": "pending until the operator approves it in tinyCRM → Approvals"}
```

The server checks the proposal against the same rules as the web app, so a
proposal that could never be applied is refused at once (`invalid proposal: …`).
Every proposal needs a `reason`; it is shown next to the change.

### Errors

A tool call fails (the client shows it as a tool error) with:

- `token invalid or revoked` — HTTP 401: revoked, expired, unknown, or not a `tc_live_` token;
- `this token may not propose changes — create one with 'Allow proposing changes'` —
  HTTP 403, from a propose tool called with a read-only token;
- `invalid proposal: <detail>` — HTTP 422: the payload failed the entity's validation;
- `not found` — HTTP 404: no such id, or it belongs to another account;
- `tinyCRM answered <status>: <detail>` — anything else, e.g. a search shorter than two characters;
- `could not reach tinyCRM: <error>` — network failure.

## Develop

```bash
cd mcp
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

The tests run the tools against a mock tinyCRM (`httpx2.MockTransport`), both
directly and through an in-process MCP client.
