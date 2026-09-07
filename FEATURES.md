# tinyCRM — Features

A single-operator CRM for self-employment: contacts, organizations, deals,
tasks, interactions, projects, documents and a watch list of sources to sweep.

FastAPI + PostgreSQL + S3 on the back, Flutter web on the front. Every row is
scoped to a `user_id` and every endpoint checks it — there are no teams, roles
or per-record permissions. Interactive API docs live at `/docs`.

Planned work is in [PLAN.md](PLAN.md); how to run and deploy it is in
[README.md](README.md) and [deploy/README.md](deploy/README.md).

---

## Entities at a glance

| Entity | What it is | Links to |
|---|---|---|
| **Contact** | A person. Address book + the fields that decide whether an approach is worth making. | organization (FK), interactions, projects, documents, tasks, deals |
| **Organization** | A company. Where a switchboard number and `office@` address belong. | contacts (FK), deals, interactions, documents, watches |
| **Deal** | An opportunity, from first sniff to finished engagement. | contact + organization (FK), interactions, documents, tasks |
| **Task** | A to-do, optionally repeating. | contact, deal, interaction (FKs), projects |
| **Interaction** | One touchpoint: call, meeting, email, note. Past = log, future = plan. | contacts, organizations, deals, projects |
| **Project** | A named piece of work with a start and end. | contacts, tasks, documents, interactions |
| **Document** | A file in S3 with metadata and a preview. | contacts, organizations, deals, projects |
| **Watch** | A source you check on a cadence: job board, careers page, tender portal. | organization (FK), watch checks |
| **WatchCheck** | One append-only sweep of one watch. | watch, created deal / task |

---

## Contacts

`GET|POST /contacts/` · `GET|PATCH|DELETE /contacts/{id}`

**Fields.** name, job_title, organization_id · email, email_secondary, phone,
phone_secondary, website · street, postal_code, city, country · birthday,
preferred_language · lifecycle_status, relation_type, source ·
known_day_rate + rate_currency, works_with_freelancers · tags, notes.

**Two axes, not one.** `relation_type` (`customer` / `partner` /
`subcontracting_target` / `contracting_authority`) is *what this party is to
me*; `lifecycle_status` (`lead` / `prospect` / `customer` / `former`) is *how
far along we are*. They filter together, so "partners we have not approached
yet" is one request — the row a single collapsed column would lose.

**`works_with_freelancers` is tri-state.** `true` / `false` / `null` = never
asked. `?works_with_freelancers=unknown` is the list that produces the next
approach; the UI shows "never asked" as grey, not red.

**Rate is a pair.** `known_day_rate` and `rate_currency` are refused half-way
in either direction, checked against the *merged* row on PATCH. Money is
`Numeric(14,2)` and a decimal string over the wire, never a float.

**Codes are normalised.** `country` is ISO 3166-1 alpha-2 upper-cased,
`preferred_language` ISO 639-1 lower-cased, so a filter cannot split "AT",
"at" and "Austria" into three countries.

**Filters.** `?search` (name) · `?organization_id` · `?lifecycle_status` ·
`?relation_type` · `?source` · `?country` · `?works_with_freelancers=yes|no|unknown`.
An unknown filter value is a 422, never silently ignored.

---

## Organizations

`GET|POST /organizations/` · `GET|PATCH|DELETE /organizations/{id}`

name, domain, email, phone, address, industry, notes. `?search` matches name
**or** domain — an email signature often gives the domain and nothing else.
Reads carry `contact_count`, computed as one correlated subquery on the list
query rather than a request per row.

`email` and `phone` here are the *company's* (`info@`, the switchboard), not a
person's. Deleting an organization is `SET NULL` on its contacts: losing the
company must never delete the people who worked there.

---

## Deals

`GET|POST /deals/` · `GET|PATCH|DELETE /deals/{id}` · `POST /deals/{id}/stage`

**Stages.** `lead → qualified → proposal → negotiation → won → running →
completed`, plus `lost`. Won ≠ finished: a long engagement stays on the board
the day the work starts.

**`?status=` is the coarse question** the UI actually asks — `open` (still
competing), `active` (on my plate, the default, includes won and running),
`won`, `finished`. `?stage=` filters one exact column.

**Value is not one number.** `value_type` picks the shape:

| value_type | fields used |
|---|---|
| `fixed` | `fixed_value` |
| `rate_based` / `retainer` | `rate` + `rate_unit`, optional `estimated_volume` + `volume_unit` |

A row priced two ways at once is refused; a quantity with no unit is refused.
Switching `value_type` on a PATCH drops the other shape's fields — that is a
re-pricing, not a contradiction.

**`expected_value` is a stored generated column**, so it cannot drift from what
it derives from. It is **NULL, never 0**, when no total exists: open-ended
deals must not be summed in as zeros. **Units are never converted** — a day
rate against a volume in months derives nothing rather than inventing a factor.

**A stage is not a label.** `_apply_stage()` is the one code path (both the
stage endpoint and PATCH route through it): arriving in a decided stage stamps
`closed_at`, pins `probability` to 100 or 0, and decides whether `lost_reason`
may exist. Sending a `lost_reason` with any stage but `lost` is a 422; one
already stored on a deal being won or reopened is cleared.

**Ordering.** Expected close date ascending, **NULLs last** — an undated deal
is not urgent.

**Filters.** `?search` (title) · `?stage` · `?status` · `?contact_id` ·
`?organization_id`.

---

## Tasks

`GET|POST /tasks/` · `GET|PATCH|DELETE /tasks/{id}`

title, description (markdown), due_date, priority 0–2, done, tags.

**Three independent links** — `contact_id`, `deal_id`, `interaction_id`, all
nullable and orthogonal. Reads carry `contact_name` / `deal_title` /
`interaction_subject` so a list says what each task is about without a request
per row. `?contact_id=` / `?deal_id=` / `?interaction_id=` answer "what do I
owe this record?". All three are `SET NULL`: deleting the person does not
silently drop the work.

**Recurrence.** `recurrence_rule` (`daily` / `weekly` / `monthly` / `yearly`),
`recurrence_interval`, `recurrence_until` (inclusive), `recurrence_parent_id`.
Deliberately not RRULE — a closed set the UI renders as a dropdown.

Completing a recurring task **creates the next instance and leaves the current
one done**, so "did I actually check in March?" stays answerable. The next due
date is computed from the *completion*, not the missed slot: finishing on time
keeps the cadence, finishing late re-anchors, so an overdue task yields exactly
one instance instead of a backlog. Month steps clamp to short months
(31 Jan + 1 month = 28/29 Feb) and the time of day is preserved. The successor
inherits description, priority, tags, project links and all three record links.

The PATCH response is `TaskCompletionRead` — it carries `next_occurrence` only
when the server actually created one, so the UI never guesses.

**Filters.** `?search` (title) · `?include_done` · the three link filters.
Ordering is due date ascending NULLs last, so overdue floats to the top.

---

## Interactions

`GET|POST /interactions/` · `GET|PATCH|DELETE /interactions/{id}`

kind (`call` / `meeting` / `email` / `note` / `other`), subject, notes,
`occurred_at`, `duration_minutes`, `done`, tags.

**`occurred_at` does double duty**: past = activity log, future = planned mail
or meeting, `done` closes the loop. One table serves both history and calendar.
`?upcoming=true` returns planned entries oldest-first (next appointment on
top); `?upcoming=false` the past log newest-first.

Attaches many-to-many to **contacts, organizations, deals and projects**.

**Filters.** `?search` (subject) · `?kind` · `?upcoming` · `?contact_id` ·
`?organization_id` · `?deal_id` · `?project_id`.

---

## Projects

`GET|POST /projects/` · `GET|PATCH|DELETE /projects/{id}`

name, description, start_date, end_date. M2M with contacts, tasks, documents;
interactions attach to it. `?search` on name.

---

## Documents

`GET|POST /documents/` · `GET|PATCH|DELETE /documents/{id}` ·
`GET /documents/{id}/content` · `PUT /documents/{id}/content` ·
`GET /documents/{id}/preview`

title, description, format (`pdf` / `markdown` / `txt`), size, storage_key,
preview_key, tags. **25 MB cap**, enforced from the recorded content length
*before* anything is read; the body then streams to S3 (multipart past 8 MB),
never one blob in memory. PDFs get a JPEG first-page preview — the one place
the whole file is materialised, because pymupdf needs it, and bounded by the
cap.

**Links are resolved before the body reaches S3.** The other order would leave
an object in the bucket with no row that could ever delete it. Multipart has no
list type, so link lists arrive as JSON arrays in form fields like `tags`; a
malformed one is a 422.

Attaches many-to-many to **contacts, organizations, deals and projects** — one
framework agreement covers two deals, and the same NDA is filed against both
the person and their company without being uploaded twice.

**Filters.** `?search` (title) · `?contact_id` · `?organization_id` ·
`?deal_id` · `?project_id`. Two at once narrow rather than widen.

---

## Watches — job boards, careers pages, tender portals

`GET|POST /watches/` · `GET|PATCH|DELETE /watches/{id}` ·
`POST /watches/{id}/check` · `GET /watches/{id}/checks`

The recurring sweep that finds work *before* there is a conversation to record.
name, url (required — a source you cannot open is not a source), kind
(`job_board` / `careers_page` / `tender_portal` / `other`), `query_note` (the
saved search in words: keywords, CPV codes, region), notes, active, optional
`organization_id`.

**Cadence reuses the task recurrence engine** (`app/recurrence.py`), not the
task table — one task per watch would put twenty identical "check X" rows in
the dashboard and bury the one real follow-up. `last_checked_at` and
`next_due_at` are stamped together by the check endpoint and nowhere else.

**The anchor differs by caller.** Logging a sweep anchors on the *scheduled*
date, keeping the rhythm; changing the cadence anchors on the *last sweep*,
because `next_due_at` by then holds a date the old rule produced. Editing the
cadence of a never-swept source leaves it due.

**`POST /{id}/check` is one transaction**: it logs the sweep, advances the
cadence, and optionally creates a deal or a task from the find. Outcome is
`nothing` or `found`; `create_deal` / `create_task` with `outcome: "nothing"`
is a 422. A refused find leaves no check, no deal and an unmoved cadence.

**"Nothing found" is a valuable answer** — it is what makes a year of diligence
on a quiet portal provable. `found_count` / `check_count` on every read answer
what a single timestamp cannot: has this source ever produced anything?
Checks CASCADE from the watch; what a find produced is `SET NULL`, so deleting
the deal does not erase the record of having found it.

**Filters.** `?due` · `?active` · `?kind` · `?search` · `?organization_id`.
Ordering is most-overdue-first, paused sources last.

---

## Cross-cutting rules

**Tenant scoping.** Every list, read, write and link is filtered by
`user_id`. Every `*_id` a client sends is validated against the caller's own
rows before it is stored — a foreign key alone would accept another tenant's
id, and since reads send the linked record's *name* back out, that would be a
data leak rather than untidy data. A miss is a **404, not a silent drop**.
`tests/test_cross_user_isolation.py` is table-driven; adding a router means
adding one row.

**Pagination.** Every list returns `Page[T]` — `items`, `total`, `skip`,
`limit` — with `limit` validated `1..200`. Every list has a **stable sort with
an `id` tiebreaker**: paging over a non-unique order lets rows repeat or vanish
between pages. The UI shows "1–25 of 213" and hides the bar when everything
fits. Pickers deliberately use `listAll()` (walking pages at `limit=200`)
because a truncated picker is the same silent bug in a smaller box.

**Deletes preserve history.** Every link between records is `SET NULL` or drops
only the join row. Deleting a company keeps its people; deleting a contact
keeps the tasks, documents and sweep logs, detached.

**Money never becomes a float.** `Numeric` in Postgres, a JSON string over the
wire, a string end to end in Dart (`core/money_text.dart`).

**Errors are one actionable sentence.** `core/error_text.dart` maps a failure
to readable text (transport vs. status, `Retry-After` on 429, the server's own
`detail` including FastAPI's validation list). `ErrorInterceptor` in `api.dart`
re-throws anything from 400 up, because `validateStatus` accepts every status
so the 401 handler can see one. Every delete goes through the same
`confirmDelete()` dialog.

---

## Screens

| Route | What it does |
|---|---|
| `/` | Dashboard: Contacts / Tasks / Upcoming panels, responsive to tabs under 700px. Contact panel filters by status, type and freelancer answer. |
| `/watches` | Sources: "Due now" / "All active" / "Everything", filter by kind. **Open & sweep** opens the source in a new tab, then offers the check dialog. Nav badge counts what is due. |
| `/deals` | List beside detail, scoped "On my plate" / "Still competing" / "Won" / "Finished" / one stage. Detail moves the deal with stage chips. |
| `/organizations` | List beside detail: contacts at the company, add-someone-here, attached documents and interactions. |
| `/projects` | Project list and detail with its contacts, tasks, documents and interactions. |
| `/documents` | Upload, pdfrx viewer, markdown render, replace content, attach anywhere. |
| `/interactions` | "Planned" vs. "Activity log". "Follow up" on a tile creates a task carrying the interaction and the person. |
| `/account`, `/account/password`, `/health`, `/login` | Profile, password change, health, sign-in. |

Contact detail is a pushed page: fields, chips for status / type / freelancer,
the address as an envelope, that contact's interactions, documents and open
tasks. A background version check prompts a reload when the deployed build hash
changes.

Shared widgets worth knowing: `RecordPicker` / `AttachmentPickers` (the four
attach pickers used by every form), `LinkedTasksSection`, `PaginationBar`,
`AttachedDocumentsSection`, `AttachedInteractionsSection`.

---

## The morning briefing

Weekday mornings, 07:00, one Slack message: overdue tasks, what is due today,
today's planned interactions, planned interactions never confirmed, and the
sources due to be swept.

`app/briefing.py` gathers and renders, `scripts/send_briefing.py` runs it,
`charts/tinycrm/templates/briefing-cronjob.yaml` schedules it on the backend
image. **No scheduler inside the API** — an in-process loop fires once per
replica, and a delivery that quietly stops looks exactly like a quiet week. A
Job fails visibly. `startingDeadlineSeconds` skips a missed slot rather than
queueing yesterday's briefing on top of this morning's.

**The day boundary is the operator's, not UTC.** Task due dates are filed as
23:59 local, which is 21:59Z in summer, so a UTC "today" puts a task due
tonight in tomorrow's message. `DayWindow` is local midnight to local midnight
— 23 or 25 hours long across a DST switch — and `days_late` counts calendar
days. `BRIEFING_TIMEZONE` must equal the CronJob's `timeZone`.

Watches appear as "due today", not "due now": a source due at 15:00 belongs in
the 07:00 message. Paused sources never appear.

```bash
cd backend
uv run python scripts/send_briefing.py --dry-run   # print it, send nothing
uv run python scripts/send_briefing.py             # needs SLACK_WEBHOOK_URL
```

Off by default in the chart (`briefing.enabled`): a CronJob that fails every
morning is worse than none.

---

## Auth and hardening

- **JWT bearer** via fastapi-users. No register / verify / reset routers are
  mounted; the admin is created with `scripts/create_admin.py`.
  `/auth/jwt/login`, `/auth/jwt/logout`, `/users/me`, `/users/me/password`.
- **Token lifetime is 270 days** with no refresh and no denylist — see T24 in
  [PLAN.md](PLAN.md).
- **Login throttle** (`app/ratelimit.py`): sliding window of *failed* logins per
  client address, `LOGIN_MAX_FAILURES` (10) per `LOGIN_FAILURE_WINDOW_SECONDS`
  (300). Over budget → 429 with `Retry-After`. Counted in middleware, because a
  dependency runs before the handler and cannot see whether the credentials were
  accepted. Every failure logs at WARNING with the source address.
  **Requires `FORWARDED_ALLOW_IPS`** wherever Caddy fronts the API, or every
  user shares one bucket — which in turn requires the backend port not to be
  publicly reachable.
- **Insecure-default guard.** `check_secure_defaults()` runs in the lifespan
  hook. Development warns per problem; **production logs each at ERROR and
  aborts startup with exit code 3**. Covers the placeholder JWT secret,
  `CORS_ORIGINS=["*"]` and the `minioadmin` MinIO credentials.
  The guard is inert unless `ENVIRONMENT=production` is set.
- **SQL echo is off by default** — `echo=True` logs every statement with its
  bound parameters, i.e. contact names, emails and notes.

---

## Configuration

All via env or `backend/.env` (see `.env.example`).

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` turns the default-guard warnings into a refusal to start |
| `DATABASE_URL` | local compose | asyncpg URL |
| `DB_ECHO` | `false` | leave off — echo logs personal data |
| `CORS_ORIGINS` | `["*"]` | must be the real origin in production |
| `JWT_SECRET` | placeholder | `openssl rand -hex 32` |
| `JWT_LIFETIME_SECONDS` | 270 days | keeps the Android PWA logged in |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW_SECONDS` | 10 / 300 | failed logins only |
| `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` / `S3_REGION` | MinIO locally | bucket versioning is checked at boot |
| `SLACK_WEBHOOK_URL` | unset | without it a real briefing send exits 2 |
| `BRIEFING_TIMEZONE` | `Europe/Berlin` | must match the CronJob's `timeZone` |
| `APP_URL` | unset | the "Open tinyCRM" link in the briefing |
| `GIT_COMMIT` | `unknown` | injected at image build, served by `/version` |

`GET /health` returns 200 `{status: ok, db: ok}` or **503** when the database
is unreachable. `GET /version` returns the running commit and build timestamp;
the frontend polls it to prompt a reload after a deploy.

---

## Tests

- **Backend: 282 tests** (`cd backend && uv run pytest`). A scratch Postgres
  database per session; tables rebuilt from the models before each test; two
  accounts (Alice and Bob) with tokens minted straight from the JWT strategy.
  S3 is faked in memory for document tests. `uv run mypy app tests` is clean and
  gated in CI; `ruff check` and `ruff format --check` too.
- **Frontend: 10 test files** (`cd frontend && flutter test`) covering the
  hand-written models, money and date formatting, and error text.
  `widget_test.dart` is browser-only — add `--platform chrome`.
- **`ci/smoke.sh`** drives the real built images against Postgres and MinIO:
  health, matching versions, the Flutter bundle and its SPA fallback, admin
  creation, login, a 401 for anonymous requests, contact / document / deal /
  watch round-trips, and the briefing script's `--dry-run` inside the image.

---

## Build and ship

- **CI** (`.github/workflows/ci.yml`, on PR into `main`): backend tests +
  frontend tests → build and push `ci-<short-head-sha>` → integration test with
  `compose.ci.yml` and `ci/smoke.sh`. A PR comment carries pass/fail counts,
  failing test names and coverage.
- **Promote** (`.github/workflows/promote.yml`, on merge to `main`): re-tags
  the *same digest* that passed the integration test to `<short-main-sha>` and
  `latest`. Nothing is rebuilt, so nothing can drift between test and release.
- **Deploy**: Flux, pull-based. `deploy/flux/` + `charts/tinycrm/`. Merging to
  `main` is the deploy; no cluster credentials live in GitHub. Rollback is
  `helm -n tinycrm rollback tinycrm`, and a failed upgrade rolls itself back
  after three retries.
- **Migrations** run as a Helm pre-upgrade hook (and a one-shot `migrate`
  service in compose), never from the backend image's `CMD` — under a rolling
  update every starting replica would race the same migration.
- **Backups**: Hetzner server snapshots (seven rolling) plus a daily CronJob
  writing one `tiny-crm-<TS>.tar` — a brotli'd `pg_dump` plus the raw MinIO
  objects — to Google Cloud Storage through its S3 endpoint. Restore rehearsed
  2026-09-05 into a throwaway kind cluster; procedure in the infrastructure
  repo's `scripts/niecke-it/RESTORE.md`. **A failed backup run is still
  silent** — the known gap, with a monthly freshness check as the interim.
