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
| Contact | name, email, phone, address *(single string)*, tags, notes | → organization (FK), ← interactions (M2M), ← projects (M2M) | CRUD, `?search` on name, `?organization_id` |
| Organization | name, domain, email, phone, address, industry, notes | ← contacts (FK) | CRUD, `?search` on name or domain, `contact_count` on read |
| Interaction | kind (call/meeting/email/note/other), subject, notes, occurred_at, duration_minutes, done, tags | M2M contacts | CRUD, filters: search, contact_id, kind, upcoming |
| Task | title, description (markdown), due_date, priority 0–2, done, tags, recurrence (rule / interval / until / parent) | → contact, deal, interaction (nullable FKs), ← projects (M2M), ← previous instance of a series | CRUD, `?search`, `?include_done`, `?contact_id`, `?deal_id`, `?interaction_id` |
| Project | name, description, start_date, end_date | M2M contacts, tasks, documents | CRUD, `?search` on name |
| Document | title, description, format (pdf/md/txt), size, storage_key, preview_key, tags | ← projects (M2M) | CRUD + upload, replace-content, download, JPEG preview |
| User | fastapi-users base + name, password_changed_at | owns everything | `/users/me`, `/users/me/password`, JWT login/logout |

`Interaction.occurred_at` does double duty: past = activity log, future = planned mail/meeting, `done` closes the loop. One table serves both history and calendar.

Screens: `/` dashboard (Contacts / Tasks / Upcoming, responsive → tabs under 700px), `/projects`, `/documents` (pdfrx viewer, markdown render), `/interactions` (Planned vs. Activity log), `/account`, `/health`, `/login`. Contact detail is a pushed page showing fields + that contact's interactions. Background version check prompts a reload when the deployed build hash changes.

### Original phase plan vs. reality

- Phase 0 Setup — **done**
- Phase 1 Contacts CRUD — **done** (API paginates; the UI never sends `skip`)
- Phase 2 Auth — **done**
- Phase 3 Interactions & Tasks — **done**: interactions link to contacts, tasks link to contacts, deals and interactions (T14); no nested `/contacts/{id}/interactions` routes (query params instead)
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

- [x] **T07 · P2 · Human-readable errors and consistent delete confirmation**
      Error states rendered `'Error: $e'` — a raw Dio stack description — and deletes confirmed or not depending on the screen.
      *Done:* `core/error_text.dart` maps a failure to one actionable sentence (transport vs. status, `Retry-After` for 429, and the server's own `detail` when there is one, including FastAPI's validation list) plus `showErrorSnackBar()` for in-place reporting; `widgets/confirm_dialog.dart` gives every delete the same `confirmDelete()` dialog — task and interaction deletes now ask, like contacts, projects and documents already did. Mutations that previously threw into the void (done-toggles, link edits, all four form saves, upload) now report and, on a form, stop the button spinning.
      *Load-bearing detail:* `validateStatus` accepts every status so the 401 handler can see one, which meant error bodies flowed into the repositories and blew up as cast errors — that, not the HTTP status, was what reached the UI. New `ErrorInterceptor` in `api.dart` turns anything from 400 up back into a thrown `DioException`, so `errorText()` has something real to read.
      *Tests:* `frontend/test/error_text_test.dart` (8 cases).

### B — Safety net (do before the model grows)

- [x] **T08 · P0 · Backend test suite**
      pytest, pytest-asyncio, httpx and mypy strict were configured; `backend/tests/` did not exist. Every endpoint reimplements the same `user_id` ownership check by hand, and one missed comparison leaks another tenant's data.
      *Done:* 80 tests, ~17s, 88% line coverage. `tests/conftest.py` creates a scratch Postgres database per session (`TEST_DATABASE_URL`, default the local compose server), rebuilds the tables from the models before each test, overrides `get_session`, and hands out two accounts — Alice and Bob — whose tokens are minted directly from the JWT strategy so password hashing stays out of the hot path.
      **Cross-user isolation is table-driven** (`tests/test_cross_user_isolation.py`): contacts, tasks, projects, interactions and documents each get read / change / delete / list / anonymous checks from Bob's side, plus owner-only checks on document content and preview. Adding a router means adding one row to `RESOURCES`. Per-router files cover CRUD round-trips, filters (done, upcoming, search, kind) and validation; `test_auth.py` and `test_users.py` cover login and the password-change flow; the earlier unit tests remain.
      *Deliberate scope:* the schema comes from `Base.metadata` rather than Alembic (`alembic check` already proves they agree, and `ci/smoke.sh` runs the real migrations in a container), and S3 is faked in memory for the document tests (the real MinIO round-trip is also in `ci/smoke.sh`).
      *Reporting:* both suites emit machine-readable results in CI; `ci/pr_report.py` renders them into the job summary and a single, updated PR comment with pass/fail counts, failing test names and line coverage.

- [x] **T09 · P0 · CI gate before the image build**
      Both workflows went straight to `docker build`; nothing blocked a broken `main`.
      *Done:* `.github/workflows/ci.yml` replaces the two per-component build workflows. On a PR into `main`: **Backend tests** (`ruff check`, `ruff format --check`, `pytest`) and **Frontend tests** (`flutter analyze`, `flutter test`, in the same SDK digest the image builds with) must pass before **Build backend** / **Build frontend** push `ci-<short-head-sha>` to the registry, and **Integration test** then starts those exact images with Postgres and MinIO (`compose.ci.yml`, own project name) and drives `ci/smoke.sh` through login, a contact round-trip and a document round-trip. The only trigger is `pull_request`: while a PR is open every dev push already fires `synchronize` on the same commit, so a `push: dev` trigger would double every run — open the PR as a draft to get CI from the first commit.
      `.github/workflows/promote.yml` runs on merge to `main` and only re-tags: it resolves the merged PR's head sha (GitHub API, merge-parent fallback), then `docker buildx imagetools create` copies that manifest to `<short-main-sha>` and `latest`. The digest that passed the integration test is the digest that deploys — nothing is rebuilt, so nothing can drift between test and release.
      **Still to do in GitHub settings:** make `Backend tests`, `Frontend tests`, `Build backend`, `Build frontend` and `Integration test` required status checks on `main`, and stop allowing direct pushes — the promote workflow has no images to promote for a commit that never went through a PR.
      *Note:* `mypy` is deliberately **not** in the gate yet — see T35.

- [x] **T35 · P1 · Get mypy green, then gate on it**
      `uv run mypy app` reported 20 errors, so it could not be a required check without being red from day one.
      *Done:* `uv run mypy app tests` is clean (45 files) and runs as a **Type-check** step in the **Backend tests** job. The test client also moved from `httpx` to **`httpx2`** (Pydantic's maintained continuation — httpx itself has gone quiet); the API is unchanged, so it was an import rename, and `httpcore` dropped out of the lock with it. Almost all of it was one root cause: `storage.py` splatted `**_client_kwargs()` into `session.client()`, which defeats the typed overloads in types-aioboto3, and the resulting `# type: ignore[arg-type]` comments were themselves wrong (the real code is `call-overload`), which cascaded into eight *unused-ignore* errors that hid a real mismatch — the config object was botocore's `Config` where aiobotocore expects `AioConfig`. Spelling the arguments out and using `AioConfig` removed all 16 errors in that file with no ignore comments left. `projects.py` needed `_load_scoped` to return `list[T]` rather than bare `list`; pymupdf's unannotated calls are covered by `untyped_calls_exclude = ["pymupdf"]` in `pyproject.toml` (results are still type-checked, only the calls are exempt) plus one typed local for the JPEG bytes. `tests/__init__.py` makes the suite a package so mypy stops seeing `conftest` twice.

- [ ] **T10 · P0 · Backups with a rehearsed restore**
      The nightly-backup plan died with the move from SQLite to Postgres.
      *In place* (infrastructure repo, `scripts/niecke-it/`): `tiny-crm-backup.sh` runs hourly from cron on the VM and uploads a pair of timestamped objects — a gzipped `pg_dump` of the whole `crm` database and a tarball of the documents bucket — to `gs://niecke-it-tiny-crm-backups` (14-day lifecycle delete, terraform `tiny-crm-backups.tf`). `BACKUP.md` documents what it writes, how to check it is still running, and the gaps; `RESTORE.md` walks a backup back into the local compose stack, including the MinIO key mapping.
      *Missing before this can be ticked:*
      1. **The restore has never actually been run.** Do it once into a clean stack, then record the date and anything surprising in `RESTORE.md`.
      2. **No alerting.** A failing cron job is invisible — the log lives on the VM and nobody reads it. Needs a dead-man's-switch ping on success plus an alert on silence (the SCC Slack webhook already exists).
      3. **Backups live in the project they protect.** At minimum a bucket retention policy so nothing can delete them early; better, a copy outside the `niecke-it` project.
      *Done when:* a restore into an empty database has actually been performed once and the steps are written down here.

- [ ] **T11 · P1 · Deployment in the repository**
      Images are built and pushed; how they reach the server is manual and undocumented.
      *Done when:* a deploy workflow plus a production compose file live in the repo, and a rollback is one command.

### C — Make it a CRM

- [x] **T12 · P0 · Organizations as a first-class entity**
      `Contact.company` was free text, so "everyone at ACME", "all deals with ACME" and "which invoice address" were unanswerable, and two spellings made two companies.
      *Done:* `Organization` (name, domain, **email, phone**, address, industry, notes) with its own `/organizations` CRUD router, `?search` over name *or* domain — an email signature often gives the domain and nothing else — and a `contact_count` per row, computed as one correlated subquery on the list query rather than a request per row. `Contact.company` is gone, replaced by `Contact.organization_id`; reads also carry `organization_name`, denormalised so a contact list shows the company without a second request, and `/contacts/?organization_id=` answers "everyone at ACME".
      **email and phone are the company's, not a person's** — `info@`, `office@` and the switchboard had nowhere to live before, and filing them on whichever contact happened to be first is how a CRM loses them.
      *Migration `3f9a1c47b2d8`* backfills one organization per distinct company string **per user**, matching case-insensitively and ignoring surrounding whitespace, so "ACME", "acme " and " Acme" collapse into one company instead of three; contacts whose company was blank stay unlinked. The downgrade writes the organization name back into a restored `company` column before dropping the table, so the step is reversible. Verified both ways against a scratch database, and `alembic check` agrees with the models.
      *Load-bearing detail:* the FK alone would accept any existing id, filing a contact under **another tenant's** company and leaking that company's name back on every read — so both create and update validate `organization_id` against the caller's own rows and 404 otherwise. `ON DELETE SET NULL`, not CASCADE: deleting a company must never delete the people who worked there.
      *Tests:* `backend/tests/test_organizations.py` (13 cases: CRUD, paging, search by name and domain, the contact link and its counts, cross-tenant refusal, delete-keeps-contacts), organizations added to the table-driven cross-user isolation suite, plus `frontend/test/organization_test.dart` for the model parsing. `ci/smoke.sh` files its smoke contact under a smoke organization.
      *UI:* `/organizations` list beside detail (contacts at the company, add-someone-here), and the contact form's free-text Company field is now a picker with a "new organization" shortcut.
      *Blocks:* T13.

- [x] **T13 · P0 · Deals and a pipeline**
      The biggest hole. Nowhere to record that a conversation became an opportunity, what it is worth, when it might close, or whether it was won.
      *Done:* `Deal` with its own `/deals` CRUD router plus `POST /deals/{id}/stage`, nullable FKs to contact *and* organization — both validated against the caller's own rows, like T12 — and `contact_name` / `organization_name` denormalised onto reads so a list row shows who the deal is with without a request per row. Filters: `?search` on title, `?stage=` for one exact column, `?status=` for the coarse question, `?contact_id=`, `?organization_id=`. Sorted by expected close date ascending with **NULLs last** — an undated deal is not urgent — and `id` as the paging tiebreaker.
      **Value is not one number**, as specified: `value_type` (`fixed` / `rate_based` / `retainer`), `fixed_value` for the first, `rate` + `rate_unit` for the others, and `estimated_volume` + `volume_unit` where **null volume = genuinely open-ended**. The router refuses a row that is priced two ways at once — a contract sum *and* a day rate cannot both be summed into a pipeline without silently picking one — and refuses a quantity with no unit, since "60" is not an estimate. Switching `value_type` on a PATCH drops the other shape's fields, because that is a deliberate re-pricing rather than a contradiction.
      `expected_value` is a **stored Postgres generated column**, not an application field, so it cannot drift from what it derives from and T28 can `SUM` it directly. It is **NULL, never 0**, when no total exists. Verified in SQL: five deals across all shapes give `sum = 84,500.00, count(*) FILTER (WHERE expected_value IS NULL) = 2` — the "€48k across 4 deals, plus 2 open-ended" shape the plan demands, with no open-ended deal contributing a zero. The UI carries the same rule: an open-ended deal's list row reads `800.00 EUR/day · open-ended` rather than blank, so a real deal at a known rate never looks like an unpriced one.
      **Units are never converted.** A day rate against a volume estimated in months derives nothing rather than inventing a days-per-month factor — that factor would be the same silent lie the single `value` column was. The form says so in place, and defaults the volume unit to the rate unit so the mismatch is deliberate rather than accidental.
      **Won ≠ finished**, so the stage enum runs `lead → qualified → proposal → negotiation → won → running → completed`, plus `lost`. `closed_at` records when the deal was *decided*: winning stamps it, starting and finishing the work leave it alone, and flipping between won and lost re-stamps it because that is a new decision. `?status=active` — the screen's default — is everything not finished, which deliberately includes won and running, so a long engagement never leaves the board the day the work starts.
      *Load-bearing detail:* a stage is not a label. Arriving in a decided stage stamps `closed_at`, pins `probability` to 100 or 0 so a weighted pipeline stops forecasting money already banked or already gone, and decides whether a lost reason may exist. All of it lives in one `_apply_stage()`, which **the stage endpoint and `PATCH` both route through** — two code paths applying different rules would make a deal's history depend on which button was pressed. A `lost_reason` the caller *sends* with any stage but `lost` is a 422; one already stored on a deal being won or reopened is cleared, not rejected.
      *Money is `Numeric`, never a float*, and Pydantic serialises it as a JSON string — so the Dart side keeps every amount a string end to end (`core/money_text.dart`) rather than parsing it into a double that cannot hold 0.10.
      *Migration `4b7e2d91c6fa`* creates the table and the generated column; nothing to backfill, since there was nowhere a deal could previously have been recorded. `SET NULL` on both FKs — deleting a customer must never delete the record of what was sold to them. Verified up, down and up again against a scratch database with rows in the table, and `alembic check` reports no drift from the models.
      *Tests:* `backend/tests/test_deals.py` (38 cases: CRUD, all three value shapes and their derived totals, open-ended and mismatched units, the contradiction refusals, every stage transition and its side effects, the PATCH/stage-endpoint equivalence, all four status filters, NULLs-last ordering, cross-tenant refusal on both FKs), deals added to the table-driven cross-user isolation suite, `frontend/test/deal_test.dart` (33 cases incl. the money formatter and unknown stages/units falling back rather than throwing). `ci/smoke.sh` round-trips a fixed deal, asserts an open-ended one has no total, and walks won → running checking the close date holds.
      *UI:* `/deals` list beside detail, scoped by "On my plate" (the default) / "Still competing" / "Won" / "Finished" / one exact stage; the detail moves a deal with a row of stage chips calling the stage endpoint, prompting for an optional reason on a loss. The form shows only the fields belonging to the chosen pricing shape, so it cannot compose a request the API will refuse.
      *Deliberately deferred:* no aggregate endpoint — the pipeline total and its open-ended count are T28, and the generated column is what makes that one query. Kanban board can follow.
      *Depends on:* T12.
      *Extended by:* T38 — public tenders are deals with extra fields, not a second entity.

- [x] **T14 · P0 · Link tasks to contacts, deals and interactions**
      Tasks attach only to projects. A CRM follow-up is always about someone — "call Maria back on Thursday".
      *Done:* three independent nullable FKs on `Task` — `contact_id`, `deal_id`, `interaction_id` — with `contact_name` / `deal_title` / `interaction_subject` denormalised onto reads so a task list says what each one is about without a request per row. All three optional and orthogonal: a task about a tender with no named contact is normal, so is a birthday reminder with no deal, and a plain to-do links to nothing. List filters `?contact_id=`, `?deal_id=`, `?interaction_id=` answer "what do I owe this record?" — the question tasks-on-projects could not.
      *Load-bearing detail:* each id is **validated against the caller's own rows**, not just the FK. The FK alone would accept any existing id, and since reads carry the linked record's *name* back out, an unvalidated link is a cross-tenant data leak rather than just untidy data. Same check `contacts.py` runs on `organization_id`. On PATCH only links the caller actually sent are checked, so clearing one to null always works and an untouched link is neither re-validated nor dropped.
      **`SET NULL` on all three**, like every other link in the app: deleting the person, the deal or the call must not silently drop work the operator committed to. The task survives, unattached. Verified at the database level, not just through the API.
      **A repeating task carries its links onto the next instance.** `_spawn_next_occurrence` copies them alongside the recurrence fields, or "check in with Maria monthly" would quietly detach itself from Maria the first time it was completed — the bug that would have made T39 and T14 silently incompatible.
      *Migration `i9j0k1l2m3n4`* adds the three columns, their indexes and their FKs; nothing to backfill. Verified up, down and up again against a scratch database with a linked row in the table, and `alembic check` reports no drift from the models.
      *Tests:* `backend/tests/test_task_links.py` (15 cases: the round trip and its denormalised names, independence of the three, add/clear, an untouched link surviving an unrelated PATCH, unknown and cross-tenant targets refused on both create and patch, the three filters, `include_done` still applying to them, parametrised delete-keeps-the-task for all three, and the recurrence hand-off), plus `frontend/test/task_links_test.dart` (5 cases). `ci/smoke.sh` creates a linked task, filters by contact, then deletes the contact and asserts the task survived detached.
      *UI:* a reusable `LinkedTasksSection` — open follow-ups plus an "Add" that pre-fills the link — on **contact detail** (the named deliverable) and on **deal detail**. The task form gets contact and deal pickers over the full unpaged lists (new `allDealsProvider`). The interaction link is deliberately *not* a picker: you do not choose one out of a dropdown of near-identical rows called "Call", so it is set by a **"Follow up" button on an interaction tile** — which carries the interaction *and* the person it was with — and shown on the form as a clearable read-only row. The dashboard task tile now shows what each task is about.
      *Blocks:* T15 — the timeline now has tasks it can merge in.

- [ ] **T15 · P1 · Unified timeline on contact detail**
      Contact detail shows interactions only. Merge interactions, tasks, deals, documents and field changes into one reverse-chronological history — the view that answers "where are we with this person?". Becomes the app's main screen.
      *Depends on:* T14.

- [ ] **T16 · P1 · Attach documents and interactions to any record**
      Documents link to projects only; a signed contract belongs to a deal, an NDA to a contact. Interactions cannot attach to a project or deal at all.
      *Also unblocks:* T38 — a tender is mostly a pile of PDFs.

- [ ] **T17 · P1 · Contact fields a business actually files**
      Missing: job title, second email/phone, website, lifecycle status (lead / prospect / customer / former), source (referral, inbound, event), preferred language, birthday. Split `address` into street / postcode / city / country so it can feed letters, invoices and vCards.
      *Same migration, domain-specific half* — a solo contractor's address book is also a partner list, so these ride along rather than becoming a second `ALTER TABLE`:
      · `relation_type` (customer / partner / subcontracting target / contracting authority) — orthogonal to `lifecycle_status` above: type is *what this party is to me*, status is *how far along we are*. Keep both; collapsing them loses "partner we have not approached yet".
      · `known_day_rate` + `rate_currency` — the freelance rate as heard, not a quote.
      · `works_with_freelancers` (bool, nullable = unknown) — the single field that decides whether an approach is worth making at all. Nullable matters: "no" and "never asked" are different answers.
      *Filterable from day one*, or the fields are decoration — see T30.

- [ ] **T36 · P0 · Contact channel compliance — may I write to this person at all?**
      Nothing in the model records whether an *unsolicited* electronic approach to a given contact is lawful. Austria's §174 TKG 2021 bans unsolicited email and calls for direct marketing without prior consent, and it covers **legal entities too** — `office@firma.at` is not a free target — with a public-register (ECG list) check on top. The fine is real, and the mistake is invisible: nothing in a normal CRM stops you, and you only find out afterwards.
      *Scope:* on `Contact` (and `Organization`, which is where a switchboard address lives):
      · `first_contact_basis` enum — `postal_or_in_person_only` (default, the safe assumption) / `public_tender` (they invited offers) / `consent_given` / `existing_relationship` (§174(4): address obtained during a sale, own similar goods, opt-out was offered).
      · `consent_since` (date, nullable) and `consent_source` (short text — where it came from, because "we have consent" without provenance is not a defence).
      · Optional `do_not_contact` hard flag that overrides everything.
      *Done when:* the value is visible **at the point of action, not buried in a detail tab** — the compose/`mailto:` affordance (T21) is disabled with the reason shown when the basis is `postal_or_in_person_only`, and the contact list shows the state as a chip. A field nobody sees at the moment of writing prevents nothing.
      *Deliberately not automated:* no ECG-list lookup, no legal advice in the app. This records a judgement the operator made; it does not make it.
      *Why it earns P0 for this app:* it is the one feature a general-purpose CRM does not have, and the failure mode it prevents is a fine plus a burned first impression with exactly the partner you wanted.
      *Related:* T21 (the send path it gates), T33 (GDPR mechanics — adjacent, not the same thing: T33 is about data subjects' rights, this is about permission to send).

- [ ] **T37 · P2 · Direction on interactions**
      `Interaction` records kind, subject, notes and time, but not who started it — so "I wrote three times and heard nothing" and "they keep asking" look identical in the log, and no follow-up rule can be built on it.
      *Scope:* `direction` enum (`outbound` / `inbound` / `internal`, default `outbound` for the existing rows — every logged touchpoint so far was one the operator made), shown as an arrow in the timeline, filterable.
      *Cheap:* one nullable column, one migration, no new entity. The rest of the activity log already exists.
      *Feeds:* T15 (timeline), T28 (dashboard: "contacts awaiting a reply").

- [ ] **T38 · P1 · Public tenders as a deal flavour**
      Vergabe opportunities (`ausschreibung`) do not fit the plain deal shape: they have a hard deadline, a procedure type, and a go/no-go that depends on whether the operator can bid alone.
      *Scope — extra columns on `Deal` (T13), not a parallel entity:* `deal_kind` (`direct` / `tender`), `contracting_authority` (FK to organization — reuse T12, do not re-type the buyer), `cpv_type` (service / supply / labour leasing), `procedure`, `submission_deadline`, `sme_suitable`, `consortium_allowed` (ARGE), `multi_role`, and the decision pair `fit` (`solo` / `consortium_only` / `no`) + `fit_reason` (one sentence, required when `fit` is set — a verdict without a reason is unusable three months later).
      *Rationale for folding into `Deal`:* a tender is an opportunity with a deadline and a bid/no-bid gate. A second entity would duplicate the pipeline, the contact links, the document links and the whole UI, and then need merging when a tender turns into an actual engagement. `deal_kind` plus a conditional form section costs one column.
      *Links:* contacts (who is on it) via T13's FKs, the PDFs via T16 (documents on any record). `submission_deadline` must reach T20's reminder job — a missed tender deadline is the single most expensive thing this app can fail to do.
      *Depends on:* T13, T16.

- [x] **T39 · P1 · Recurring tasks**
      `Task.due_date` existed; recurrence did not, so "check the ORF winners' job pages monthly" and "follow up with EBCONT in two weeks" had to be retyped after every tick — which means they stop happening.
      *Done:* `recurrence_rule` (`daily` / `weekly` / `monthly` / `yearly`), `recurrence_interval`, `recurrence_until` and `recurrence_parent_id` on `tasks`; the arithmetic lives in `app/recurrence.py` with its own unit tests. Deliberately **not RRULE** — four cadences plus an interval are a closed set the UI renders as a dropdown, and the column can grow into an RRULE string later without changing how completion works.
      **Completing a recurring task creates the next instance and leaves the current one done**, so "did I actually check in March?" stays answerable; `recurrence_parent_id` chains the instances (`ON DELETE SET NULL`, so deleting one completed instance does not take the series with it) and doubles as the guard that ticking a task done, undone and done again cannot fork the series. The successor inherits description, priority, tags, the recurrence settings and the task's project links.
      *Next due date is computed from the completion, not the missed slot:* finishing early or on time keeps the cadence (due on the 1st, ticked off on the 28th → due the 1st again), finishing late re-anchors on the completion (a monthly check-in last due in March, done in June, is next due in July), so an overdue task yields exactly one instance instead of a backlog. Month steps clamp to the end of shorter months (31 Jan + 1 month = 28/29 Feb) and the user's time of day is preserved. `recurrence_until` is inclusive; past it the series simply stops.
      *Validation* is on the merged state, so a PATCH cannot leave a rule without a due date to repeat from, and an end date before the due date is refused. The PATCH response carries `next_occurrence` — the UI reports the new due date only when the server actually created one, rather than guessing that a repeat happened.
      *Still open:* the reminder half. A recurrence that only surfaces in an open browser tab is still passive — see T20.
      *Pairs with:* T20 (a reminder that never leaves the browser makes recurrence pointless).

- [ ] **T40 · P2 · Job-watch list**
      For companies worth watching without an active conversation: are they hiring for roles that imply the work the operator does?
      *Scope:* on `Organization` — `careers_url`, `jobs_checked_at`, `relevant_role_seen` (bool) plus a short note. Three columns, no module, no scraper.
      *Done when:* an "unchecked longest" list exists, and marking one checked is one tap. Combined with T39 that is the whole feature: a recurring task points at the list.
      *Explicitly not:* crawling careers pages. That is a different project with a different failure mode.

- [ ] **T18 · P0 · One search across everything**
      Search is per-panel and matches exactly one column each — a contact is unfindable by email, phone or note text. Postgres full-text (`tsvector` + GIN, or `pg_trgm` for fuzzy names), not the FTS5 the original plan assumed.
      *Done when:* a single search box in the app bar returns contacts, organizations, interactions, tasks, deals and documents.
      *Do after:* T12–T14, so the model has settled.

- [ ] **T19 · P0 · Import and export**
      No way to get data in or out except by typing. CSV import with column mapping and a dry-run preview, CSV export per entity, vCard in/out for contacts. Also the GDPR data-portability answer and the escape hatch that makes a self-hosted CRM safe to adopt.

- [ ] **T20 · P1 · Reminders that leave the browser**
      Overdue tasks and planned meetings are only visible if the app is open, which makes the "Upcoming" panel passive. Needs a scheduled job plus an outbound mail sender: due-today digest, overdue nudge, meeting reminder.
      *Also carries:* tender submission deadlines (T38) and recurring-task instances (T39) — both are worthless without a nudge that leaves the browser.
      *Shares infrastructure with:* T21, T23.

- [ ] **T21 · P1 · Log an email without syncing mailboxes**
      Full IMAP sync stays out of scope. The 80%: `mailto:` links from a contact, a "log this email" form, and a BCC-to-inbox address that files a message as an interaction.
      *Gated by:* T36 — the `mailto:` affordance is where channel compliance has to bite, or the field is decoration.

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
      *Open-ended deals count separately* (T13): sum what has an `expected_value`, then show "+ n open-ended" beside it. Never fold them in as zero.

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
2. **T08** — the rest of the test suite (the CI gate that runs it landed with T09).
3. **T10** — backups. Unblocks nothing, which is exactly why it gets deferred forever.
4. **T12 → T13** — Organizations, then Deals. Turns a contact book into a CRM.
5. **T14 → T15** — link tasks, then build the timeline; it becomes the main screen.
6. **T17 + T36** — one migration on `contacts`: the business fields and the channel-compliance fields together. T36 is cheap, prevents an expensive mistake, and has no dependencies — do not let it sit behind the pipeline work.
7. **T18, T19** — search and import/export, once the model has settled.
8. **T23, T20, T22** — password reset, reminders, calendar feed. All three need outbound mail; build the sender once. T39 (recurring tasks) shipped ahead of T20; its instances stay silent until that reminder job exists.
9. **T38** — tender fields, after T13 and T16 exist. T37 and T40 are one-migration jobs; slot them into any spare afternoon.

Everything else is opportunistic.

## Guiding Principles

- **One feature at a time, fully vertical.** Model → migration → endpoint → test → UI → merged → deployed.
- **A tiny deployed app beats an elaborate localhost prototype.**
- **Resist scope creep.** If it is not on the backlog above, it goes in `IDEAS.md`, not the sprint.
