# tinyCRM

A small CRM for self-employment, built as a learning project for FastAPI and Flutter.

## Goals

- Track contacts, organizations, interactions, tasks and deals for a solo business.
- Learn FastAPI (backend) and Flutter web (frontend) end-to-end.
- Ship a real, deployed, authenticated app — not just a localhost demo.

## Deliberately Out of Scope

- Marketing automation
- Teams, roles, per-record permissions (rows are `user_id`-scoped, but there is one operator)
- Lead scoring, territories, workflow builders
- Built-in invoicing and time tracking (separate concern)
- Full mailbox sync (IMAP/Graph) — see T21 for the cheap 80% instead

---

## Stack (as built)

| Layer | Actual | Notes |
|---|---|---|
| API | FastAPI + uvicorn, SQLAlchemy 2.0 async, Pydantic v2, Alembic | JSON logging via `log_config.json` |
| Database | PostgreSQL 18 + asyncpg | Original plan said SQLite/FTS5; tags use Postgres-native `ARRAY(String)` |
| Auth | fastapi-users, JWT bearer, admin created via `scripts/create_admin.py` | No register / verify / reset routers mounted |
| Blob store | S3-compatible via aioboto3, MinIO locally | Bucket versioning checked at boot |
| Client | Flutter web, Riverpod 3, go_router 17, dio, flutter_secure_storage | Hand-written models; original plan said `freezed` |
| CI/CD | GitHub Actions → Google Artifact Registry (`europe-west1`), WIF auth, Renovate | Original plan said ghcr.io + Hetzner SSH; no deploy workflow yet |
| Serving | Caddy inside the frontend image, Podman/Docker Compose | `compose.full.yml` = db + minio + backend + frontend |

---

## Status snapshot (2026-08-25)

~1.5k LOC Python, ~5.1k LOC Dart, 6 entities, 12 migrations, **0 backend tests**.

### Built

| Entity | Fields | Links | API |
|---|---|---|---|
| Contact | name, company *(free text)*, email, phone, address *(single string)*, tags, notes | ← interactions (M2M), ← projects (M2M) | CRUD, `?search` on name |
| Interaction | kind (call/meeting/email/note/other), subject, notes, occurred_at, duration_minutes, done, tags | M2M contacts | CRUD, filters: search, contact_id, kind, upcoming |
| Task | title, description (markdown), due_date, priority 0–2, done, tags | ← projects (M2M) only | CRUD, `?search`, `?include_done` |
| Project | name, description, start_date, end_date | M2M contacts, tasks, documents | CRUD, `?search` on name |
| Document | title, description, format (pdf/md/txt), size, storage_key, preview_key, tags | ← projects (M2M) | CRUD + upload, replace-content, download, JPEG preview |
| User | fastapi-users base + name, password_changed_at | owns everything | `/users/me`, `/users/me/password`, JWT login/logout |

`Interaction.occurred_at` does double duty: past = activity log, future = planned mail/meeting, `done` closes the loop. One table serves both history and calendar.

Screens: `/` dashboard (Contacts / Tasks / Upcoming, responsive → tabs under 700px), `/projects`, `/documents` (pdfrx viewer, markdown render), `/interactions` (Planned vs. Activity log), `/account`, `/health`, `/login`. Contact detail is a pushed page showing fields + that contact's interactions. Background version check prompts a reload when the deployed build hash changes.

### Original phase plan vs. reality

- Phase 0 Setup — **done**
- Phase 1 Contacts CRUD — **done** (API paginates; the UI never sends `skip`)
- Phase 2 Auth — **done**
- Phase 3 Interactions & Tasks — **partial**: interactions link to contacts, tasks do not; no nested `/contacts/{id}/interactions` routes (query params instead)
- Phase 4 Deals & pipeline — **missing**
- Phase 5 Search & import/export — **missing** (search is single-column `ILIKE` per entity)
- Phase 6 Hardening & CI/CD — **partial**: images build and push; no lint/test job, no deploy job, no backup job
- Unplanned bonus: Projects and Documents (S3, previews, versioned bucket)

---

## Backlog

One task at a time, each independently shippable: model → migration → endpoint → test → UI → merged.
Priorities: **P0** not a CRM without it · **P1** daily friction · **P2** expected but deferrable.

### A — Fix what is already shipped

- [x] **T01 · P0 · SQL echo off by default**
      `echo=True` was hard-coded, so production logged every statement with bound parameters (contact names, emails, notes).
      *Done:* `db_echo: bool = False` in `config.py`, read by `db.py`.

- [x] **T02 · P0 · Warn when the built-in JWT secret survives into a running instance**
      *Done:* `DEFAULT_JWT_SECRET` in `config.py`, startup warning in the `lifespan` hook.

- [x] **T03 · P0 · Refuse insecure production defaults**
      `cors_origins = ["*"]` and MinIO `minioadmin/minioadmin` shipped as silent defaults alongside the placeholder JWT secret.
      *Done:* `ENVIRONMENT` setting (`development` | `production`) plus `Settings.insecure_defaults()`, checked by `check_secure_defaults()` in the `lifespan` hook. Development logs a warning per problem and continues; production logs each one at ERROR and raises `InsecureConfigurationError`, which aborts uvicorn startup with exit code 3. Supersedes the T02 warning. **Set `ENVIRONMENT=production` on the deployed instance — the check is inert without it.**

- [x] **T04 · P0 · Rate-limit login (layer 1: per-address, in-memory)**
      `/auth/jwt/login` was unthrottled, with no lockout and no failed-attempt logging.
      *Done:* `app/ratelimit.py` — sliding window of failed logins per client address (`LOGIN_MAX_FAILURES`, default 10 per `LOGIN_FAILURE_WINDOW_SECONDS`, default 300). Over budget returns `429` with `Retry-After`. Counting happens in a middleware, because a dependency runs before the handler and cannot see whether credentials were accepted; only failures consume budget, so a mistype costs nothing. Every failure logs at WARNING with the source address. No cache server: the Dockerfile runs a single uvicorn worker, so a module-level dict is process-global — the map is swept and hard-capped so a rotating-IP flood cannot grow it without bound.
      **Requires `FORWARDED_ALLOW_IPS`** on any deployment where Caddy fronts the API (set in `compose.full.yml`); without it uvicorn discards `X-Forwarded-For` and every user shares one bucket. That in turn requires the backend port not to be publicly reachable, or `X-Forwarded-For` can be forged.
      *Does not cover:* an attacker rotating source addresses — see T34.

- [x] **T05 · P1 · Stop lists truncating silently**
      API defaults were 50 contacts / 200 everything else, and the Flutter repositories never sent `skip` or `limit`, so past 50 contacts the dashboard just stopped.
      *Done:* all five list endpoints return `Page[T]` (`items`, `total`, `skip`, `limit`) via `app/schemas/page.py` and `count_rows()` in `app/db.py`; `limit` is validated `1..200`. Every list also got a **stable sort with an `id` tiebreaker** — paging over a non-unique order lets rows repeat or vanish between pages, so this was load-bearing, not cosmetic. Frontend: `PagedResult<T>` (named to avoid the clash with Flutter's own `Page`), a `PaginationBar` footer showing "1–25 of 213" that hides itself when everything fits, and per-surface `skip` state that resets to 0 whenever the query changes.
      *Pickers are separate:* contact/task/document pickers and id-to-name lookups need the whole set, so they use `listAll()` (walks pages at `limit=200`) behind `allContactsProvider` / `allTasksProvider` / `allDocumentsProvider` — paging those would have reintroduced the same silent truncation inside the pickers. These are invalidated alongside their paged counterparts.

- [x] **T06 · P1 · Stream document uploads**
      `await file.read()` buffered the whole file before the size check, so the 25 MB cap was enforced after the memory was already spent.
      *Done:* `_checked_size()` reads the length Starlette already recorded (`UploadFile.size`, falling back to a seek) and rejects with `413` before anything is read; the body then goes to S3 through `put_object_stream()` in `storage.py`, which hands the spooled file object to `upload_fileobj` — parts on the wire, multipart past 8 MB, never one blob in memory. PDF previews are the one exception and are documented as such: pymupdf needs the whole document, so `_render_preview()` materialises it — after the size check, so bounded by the cap.
      *Not covered:* Starlette parses the multipart body before the handler runs, so an oversized upload is still spooled to a temp file (disk, not memory) before the 413. Rejecting on `Content-Length` needs a middleware, like `ratelimit.py` — separate task if the disk churn matters.

- [ ] **T07 · P2 · Human-readable errors and consistent delete confirmation**
      Error states render `'Error: $e'` — a raw Dio stack description. Contact deletes confirm; task and document deletes do not.
      *Files:* `frontend/lib/pages/*.dart`.

### B — Safety net (do before the model grows)

- [ ] **T08 · P0 · Backend test suite**
      pytest, pytest-asyncio, httpx and mypy strict are configured; `backend/tests/` does not exist. Start with **cross-user isolation** — every endpoint reimplements the same `user_id` ownership check by hand, and one missed comparison leaks another tenant's data. Then auth-required, CRUD round-trip and validation per router, against a throwaway Postgres.
      *Done when:* `uv run pytest` covers all six routers, isolation included.

- [ ] **T09 · P0 · CI gate before the image build**
      Both workflows go straight to `docker build`; nothing blocks a broken `main`.
      *Done when:* a PR workflow runs `ruff check`, `ruff format --check`, `mypy`, `pytest`, `flutter analyze` and `flutter test`, and the build workflows depend on it.

- [ ] **T10 · P0 · Backups with a rehearsed restore**
      The nightly-backup plan died with the move from SQLite to Postgres. Needs scheduled `pg_dump`, offsite copies, MinIO bucket replication for documents.
      *Done when:* a restore into an empty database has actually been performed once and the steps are written down here.

- [ ] **T11 · P1 · Deployment in the repository**
      Images are built and pushed; how they reach the server is manual and undocumented.
      *Done when:* a deploy workflow plus a production compose file live in the repo, and a rollback is one command.

### C — Make it a CRM

- [ ] **T12 · P0 · Organizations as a first-class entity**
      `Contact.company` is free text, so "everyone at ACME", "all deals with ACME" and "which invoice address" are unanswerable, and two spellings make two companies.
      *Scope:* `Organization` (name, domain, address, industry, notes), `Contact.organization_id`, one-off backfill migration from the existing strings, list/detail UI.
      *Blocks:* T13.

- [ ] **T13 · P0 · Deals and a pipeline**
      The biggest hole. Nowhere to record that a conversation became an opportunity, what it is worth, when it might close, or whether it was won.
      *Scope:* `Deal` (title, value, currency, stage enum, expected_close_date, probability, won/lost + lost reason), FKs to contact and organization, a stage-change endpoint, CRUD UI. Kanban board can follow a week later.
      *Depends on:* T12.

- [ ] **T14 · P0 · Link tasks to contacts, deals and interactions**
      Tasks attach only to projects. A CRM follow-up is always about someone — "call Maria back on Thursday".
      *Scope:* nullable FKs on `Task`, create-task-from-contact in the UI.
      *Blocks:* T15.

- [ ] **T15 · P1 · Unified timeline on contact detail**
      Contact detail shows interactions only. Merge interactions, tasks, deals, documents and field changes into one reverse-chronological history — the view that answers "where are we with this person?". Becomes the app's main screen.
      *Depends on:* T14.

- [ ] **T16 · P1 · Attach documents and interactions to any record**
      Documents link to projects only; a signed contract belongs to a deal, an NDA to a contact. Interactions cannot attach to a project or deal at all.

- [ ] **T17 · P1 · Contact fields a business actually files**
      Missing: job title, second email/phone, website, lifecycle status (lead / prospect / customer / former), source (referral, inbound, event), preferred language, birthday. Split `address` into street / postcode / city / country so it can feed letters, invoices and vCards.

- [ ] **T18 · P0 · One search across everything**
      Search is per-panel and matches exactly one column each — a contact is unfindable by email, phone or note text. Postgres full-text (`tsvector` + GIN, or `pg_trgm` for fuzzy names), not the FTS5 the original plan assumed.
      *Done when:* a single search box in the app bar returns contacts, organizations, interactions, tasks, deals and documents.
      *Do after:* T12–T14, so the model has settled.

- [ ] **T19 · P0 · Import and export**
      No way to get data in or out except by typing. CSV import with column mapping and a dry-run preview, CSV export per entity, vCard in/out for contacts. Also the GDPR data-portability answer and the escape hatch that makes a self-hosted CRM safe to adopt.

- [ ] **T20 · P1 · Reminders that leave the browser**
      Overdue tasks and planned meetings are only visible if the app is open, which makes the "Upcoming" panel passive. Needs a scheduled job plus an outbound mail sender: due-today digest, overdue nudge, meeting reminder.
      *Shares infrastructure with:* T21, T23.

- [ ] **T21 · P1 · Log an email without syncing mailboxes**
      Full IMAP sync stays out of scope. The 80%: `mailto:` links from a contact, a "log this email" form, and a BCC-to-inbox address that files a message as an interaction.

- [ ] **T22 · P1 · Calendar view and `.ics` feed**
      Interactions already carry `occurred_at` and `duration_minutes`, so a month/week view is mostly presentation. A read-only iCalendar feed gets planned meetings into the calendar the operator already uses, at a fraction of the cost of real sync.

### D — Accounts

- [ ] **T23 · P0 · Password reset**
      A forgotten password today means SSH plus a Python script. fastapi-users already ships the reset and verify routers — they are simply not mounted, and no mail sender is wired up.
      *Shares infrastructure with:* T20.

- [ ] **T24 · P1 · Short-lived tokens with refresh, and a real logout**
      `jwt_lifetime_seconds` is 270 days with no refresh token and no denylist. A leaked token stays valid until it expires; changing the password does not invalidate it; logout only clears client storage.
      *Done when:* short access token + refresh token, revoked on password change and on explicit sign-out.

- [ ] **T34 · P1 · Rate-limit login (layer 2: durable per-account backoff)**
      T04 throttles per source address, which an attacker rotating IPs walks straight through, and its window resets on every redeploy. Add `failed_login_count` and `locked_until` to the user table (Postgres, no new infrastructure) so the budget follows the *account* and survives restarts.
      *Use exponential backoff* (`locked_until = now + 2^n` seconds, capped around 15 min), not a hard lock — a hard lock hands an attacker a way to lock the operator out of their own CRM on purpose.
      *Needs:* an Alembic migration on `user`.

- [ ] **T25 · P2 · User administration in the app**
      Teams stay out of scope, but every row is already `user_id`-scoped, so a second account is a UI problem, not a data-model one. At minimum: create and deactivate users without a shell.

### E — Polish

- [ ] **T26 · P2 · Archive instead of delete**
      All deletes are hard, and a deleted contact silently strips itself out of past interactions, leaving history that references nobody. `deleted_at` plus default filtering preserves the trail and makes an accidental delete recoverable.

- [ ] **T27 · P2 · Duplicate detection and merge**
      Nothing prevents entering the same person twice, and CSV import (T19) makes it routine. Warn on matching email or fuzzy name at create time; merge re-points interactions, tasks and deals.

- [ ] **T28 · P2 · Numbers on the dashboard**
      The dashboard lists records but reports nothing. A small strip: open pipeline value by stage, deals won this quarter, interactions logged this week, contacts untouched for 90 days, overdue count.

- [ ] **T29 · P2 · Change history**
      Only `updated_at` is kept, and concurrent edits silently last-write-win. An append-only audit table gives "who changed this and when" and supports optimistic-concurrency checks on PATCH.

- [ ] **T30 · P2 · Filter by tag, status and date range**
      Tags are stored on every entity and cannot be filtered by anywhere. Also: sort lists by name, last contact and due date.

- [ ] **T31 · P2 · Index the search columns**
      Every list endpoint does `ILIKE '%term%'` against a single unindexed column — a sequential scan per debounced keystroke. Superseded for search itself by T18, but the ordering and filter columns still want indexes.

- [ ] **T32 · P2 · Error tracking and metrics**
      JSON logs and `/health` exist; nothing reports a 500 without someone reading the log. Add an error tracker and request/latency metrics.

- [ ] **T33 · P2 · GDPR mechanics**
      Personal data on named individuals in the EU implies an export-everything endpoint, a real erase path (which T26 complicates), and a documented retention period. Mostly satisfied by T19 + T26, plus writing down where it is recorded.

---

## Suggested order

Dependency- and leverage-ordered, not a strict ranking:

1. **T03–T07** — close the remaining shipped issues. Days, not weeks.
2. **T08, T09** — tests and a CI gate, before the model grows.
3. **T10** — backups. Unblocks nothing, which is exactly why it gets deferred forever.
4. **T12 → T13** — Organizations, then Deals. Turns a contact book into a CRM.
5. **T14 → T15** — link tasks, then build the timeline; it becomes the main screen.
6. **T18, T19** — search and import/export, once the model has settled.
7. **T23, T20, T22** — password reset, reminders, calendar feed. All three need outbound mail; build the sender once.

Everything else is opportunistic.

## Guiding Principles

- **One feature at a time, fully vertical.** Model → migration → endpoint → test → UI → merged → deployed.
- **A tiny deployed app beats an elaborate localhost prototype.**
- **Resist scope creep.** If it is not on the backlog above, it goes in `IDEAS.md`, not the sprint.
