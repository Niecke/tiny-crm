# Dashboard — aggregated numbers

The plan for **#138**. This file exists so the task can be picked up without
re-deriving what to count; the issue is the work, this is the detail.

Today's dashboard lists records: tasks, upcoming interactions, contacts. Lists
answer "what is there", which the operator already knows. They do not answer
"is this going well", "what is stuck", or "where does the money actually come
from" — and those are the questions a solo business opens a CRM to ask.

**Scope is the backend.** The Flutter UI is being replaced, so nothing below
describes a layout, a chart or a tile. The deliverable is one endpoint whose
response a client can render directly, plus the tests that prove the arithmetic.
Where a number is genuinely useless without a particular presentation, that is
noted — but the presentation is the client's problem.

---

## The four ways to get this wrong

These are not style notes. Each one produces a number that is confidently wrong,
and a dashboard that is confidently wrong is worse than no dashboard, because it
gets believed.

1. **Open-ended deals are not zero.** `Deal.expected_value` is `NULL` when a
   deal is priced by rate with no volume estimate ([deal.py:47](backend/app/models/deal.py#L47)),
   and `NULL` rather than `0` was chosen exactly so this cannot happen silently.
   `SUM` skips them, which is correct — but the count must be reported beside the
   sum. Every money figure in this document is a **pair**: an amount, and a count
   of deals that have no derivable amount. A day-rate-heavy pipeline summed
   without that pair reads as empty.

2. **Currencies are never added.** `Deal.currency` is per deal
   ([deal.py:91](backend/app/models/deal.py#L91)) because the operator can quote
   in EUR and bill in USD. Every aggregate groups by currency and returns a list,
   even while there is one currency in the database. A single-currency assumption
   is the kind that is discovered by a wrong total, not by a test.

3. **`Decimal`, all the way to the wire.** Money is `Numeric` in the database for
   the reason stated in the model; loading it into a float for a JSON response
   undoes that at the last step. Serialise as strings, exactly as `DealRead`
   already does.

4. **"This week" is local.** [briefing.py](backend/app/briefing.py) already
   solved this: `DayWindow` computes a calendar day in `BRIEFING_TIMEZONE`, with
   an explicit note on why a UTC window misfiles a task due at 23:59 local.
   Periods here are built from the same machinery — extended to weeks, months and
   quarters — and not reimplemented. A dashboard that disagrees with the briefing
   about what happened today is a bug report waiting to be filed.

---

## Metric catalogue

Grouped by the question each group answers. The **Needs** line names the backlog
task that makes it computable; anything with no Needs line can be built against
the schema as it stands today.

### A · What is in play right now

| Metric | How |
|---|---|
| Open pipeline value, per stage | `SUM(expected_value)` over `OPEN_STAGES`, grouped by `stage` and `currency`, with the open-ended count per group |
| Open deal count, per stage | `COUNT(*)` over the same — the shape of the funnel, which the value alone hides when one big deal dominates |
| Weighted pipeline | `SUM(expected_value * probability / 100)`. **Needs #120** — `probability` is manual today and therefore mostly `NULL`, so this number is currently a sum over an arbitrary subset. Do not ship it before the per-stage defaults exist |
| Committed but not delivered | `SUM(expected_value)` over `won` and `running` — work agreed and not yet finished. The figure that answers "can I take on another project" |

### B · Is it moving

The group that does not exist today at all, and the reason #115 is P0.

| Metric | How |
|---|---|
| Median days in current stage, per stage | From `stage_changed_at`. Median, not mean — one deal parked for a year drags a mean into uselessness |
| Oldest open deal, per stage | `MIN(stage_changed_at)`, with the deal's title. A single name is more actionable than a distribution |
| Deals entering each stage this period | `COUNT` over `deal_stage_events` by `to_stage`. Throughput, as opposed to the standing snapshot in A |
| Stage conversion rate | Of deals that ever entered stage *n*, the share that reached *n+1*. Computed from the event table, which is why the table is worth having beyond the column |
| Median days lead → won | Sales cycle length. Directly answers "when will money from a conversation I start today actually arrive" |
| **Needs** | **#115** for all six |

### C · Did it come off, and why

| Metric | How |
|---|---|
| Won this period | Count and value, from `deal_stage_events` entering `won` within the window. Not `closed_at`, which moves when a deal flips from lost to won |
| Lost this period | Count and value, same source |
| Win rate by count, and by value | Two numbers, deliberately. They diverge when the big deals are the lost ones, and the divergence is the finding |
| Lost reasons, ranked | `GROUP BY lost_category`. **Needs #118** — free text cannot be grouped |
| Win rate and won value by source | `GROUP BY source`. **Needs #118** — `Deal` has no `source` today, though `Capture` and `Contact` both do. The single most decision-changing number on this page: it is what says whether the watch sweeps, the meetup, or the referrals are worth the evening |

### D · What is rotting

Risk and hygiene. Every row here should be a count that is also a link to a
filtered list — a number the operator cannot act on is decoration.

| Metric | How |
|---|---|
| Open deals with no next step | The `?stalled=true` filter. **Needs #116** |
| Open deals past `expected_close_date` | The `?overdue=true` filter — a forecast that has expired. **Needs #117** |
| Lost deals due to be revisited | `revisit_at <= today`. **Needs #118** |
| Captures waiting, and the age of the oldest | `status == "new"`. Available today; the briefing already computes it ([briefing.py:179](backend/app/briefing.py#L179)) |
| Overdue tasks | Available today, same source as the briefing |
| Planned interactions never confirmed | Available today — the log is lying until these are resolved |
| Contacts untouched for 90 days | No interaction with `occurred_at` in the last 90 days. Scope it to contacts that are worth touching rather than every row, or the number is a constant |
| Contacts awaiting a reply | Last interaction was `outbound` and nothing came back. **Needs #135** |

### E · Am I doing the work

Leading indicators. When group A is thin, this is the group that says whether
the cause was three months ago.

| Metric | How |
|---|---|
| Interactions logged this period, by kind | `GROUP BY kind` over the window |
| Outbound vs inbound | **Needs #135** |
| New deals opened this period | By `created_at` |
| Captures converted vs dismissed | Triage throughput — whether the inbox is worked or merely filled |
| Tasks completed this period | Against tasks created, so a rising backlog is visible as a trend rather than as a number |

### F · Delivery

| Metric | How |
|---|---|
| Running engagements, count and value | |
| Completed this period | |
| Projects with no activity in 30 days | |
| **Needs** | **#119** — until a project links to the deal that paid for it, none of this can be computed |

---

## Endpoint

```
GET /metrics/dashboard?period=quarter    # week | month | quarter | year
```

One request, one response, one Pydantic model per group. Reasons for a single
endpoint rather than one per metric: a dashboard assembled from twelve requests
is twelve chances to render half a page, the groups share window and
tenancy-filter computation, and a client that must issue twelve calls will cache
them inconsistently and show numbers from different moments side by side.

```jsonc
{
  "period": {"kind": "quarter", "start": "2026-07-01", "end": "2026-10-01", "timezone": "Europe/Vienna"},
  "pipeline": {
    "by_stage": [
      {"stage": "proposal", "count": 4, "currency": "EUR", "value": "48000.00", "open_ended": 2}
    ]
  },
  "velocity":  { /* B */ },
  "outcomes":  { /* C */ },
  "attention": { /* D */ },
  "activity":  { /* E */ },
  "delivery":  { /* F */ }
}
```

Notes on the shape:

- **`period` is echoed back, resolved.** The client asked for "quarter"; the
  response says which quarter, in which timezone. A number with no stated window
  cannot be checked against anything.
- **A group that is not computable yet is absent, not zero.** While #115 is
  unshipped, `velocity` is omitted entirely. An empty object reads as "nothing
  moved", which is a different and much worse claim than "not measured".
- **Every count in group D is paired with the query that produced it** (the
  filter name and its arguments), so a client can link to the list without
  re-deriving the filter and drifting from it.
- **Aggregate in SQL.** Every metric here is one grouped query; none needs rows
  loaded into Python. `count_rows` ([db.py](backend/app/db.py)) already
  establishes the pattern. The whole endpoint should be a handful of queries
  executed concurrently, not a loop over deals.
- **`user_id` scoping on every single query.** There is one operator, so a
  missing filter will never be noticed in use — which is exactly why it has to be
  caught by a test that creates a second user's rows and asserts they are absent
  from the totals. The same reasoning `_check_links`
  ([deals.py:54](backend/app/routers/deals.py#L54)) already applies to writes.

---

## Order of work

**Phase 0 — nothing new required.** Groups A (minus weighted) and E (minus
direction), plus the four rows of D that the briefing already computes. This is
the "one afternoon" version #138 was scoped as, and it is worth shipping on its
own: it proves the endpoint, the period machinery, the currency grouping and the
open-ended pair, which is most of the risk in the whole task.

**Phase 1 — after #115 / #116 / #117.** Group B, and the rest of D. The point at which
the page stops describing the pipeline and starts driving it.

**Phase 2 — after #118 and #135.** Group C in full, and outbound/inbound in E.
Win rate by source is the number to build the page around once it exists.

**Phase 3 — after #119.** Group F.

Phase 0 before the section-E tasks, deliberately: it is independent, it is small,
and having the endpoint already in place means each velocity task ships its
numbers with it rather than accumulating a second backlog of "add this to the
dashboard".

---

## Deliberately not here

- **No configurable widgets, no saved views, no date-range picker beyond the
  four periods.** One operator, one page. Configurability is a substitute for
  knowing what to show.
- **No charts specified.** The UI migration decides that. The response carries
  enough per-stage and per-period structure to draw one without the API
  committing to how.
- **No forecasting or scoring.** Lead scoring is out of scope in
  [CONTRIBUTING.md](CONTRIBUTING.md) and stays out. The weighted pipeline in group A is
  arithmetic on a number the operator typed, which is a different thing from a
  model guessing on their behalf.
- **No targets or goals.** "€X this quarter" is a feature about feelings, and it
  turns every honest number on the page into a number someone is tempted to
  manage.
