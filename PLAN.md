# tinyCRM

A small CRM for self-employment, built as a learning project for FastAPI and Flutter.

**What is already built is documented in [FEATURES.md](FEATURES.md).** This file
is only what is still open.

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
- Crawling or scraping any watched source (T40 shipped as a habit, not a scraper)

---

## Stack (as built)

| Layer | Actual | Notes |
|---|---|---|
| API | FastAPI + uvicorn, SQLAlchemy 2.0 async, Pydantic v2, Alembic | JSON logging via `log_config.json` |
| Database | PostgreSQL 18 + asyncpg | Tags use Postgres-native `ARRAY(String)` |
| Auth | fastapi-users, JWT bearer, admin created via `scripts/create_admin.py` | No register / verify / reset routers mounted |
| Blob store | S3-compatible via aioboto3, MinIO locally | Bucket versioning checked at boot |
| Client | Flutter web, Riverpod 3, go_router 17, dio, flutter_secure_storage | Hand-written models |
| Scheduling | Kubernetes CronJobs on the backup and backend images | Off-site backup; weekday morning briefing to Slack. No scheduler inside the API |
| CI/CD | GitHub Actions → Google Artifact Registry (`europe-west1`), WIF auth, Renovate | Test → build → integration test → promote-by-digest |
| Deploy | Flux (pull-based), Helm chart in `charts/tinycrm/` | Merging to `main` is the deploy |
| Serving | Caddy inside the frontend image, Podman/Docker Compose | `compose.full.yml` = db + minio + backend + frontend |

---

## Status snapshot (2026-09-07)

~4.9k LOC Python, ~11.6k LOC Dart, 9 tables of substance, 18 migrations,
**282 backend tests + 10 Flutter test files**, deployed via Flux with backups
rehearsed.

Shipped since the original plan: the full pipeline (organizations → deals →
task links → attachments anywhere), business contact fields, recurring tasks,
the watch list, the Slack morning briefing, the test suite, the CI gate, mypy
strict, backups with a rehearsed restore, and pull-based deployment. Details in
[FEATURES.md](FEATURES.md).

### The three real gaps

1. **No search across anything** (T18) and **no way in or out but typing** (T19).
2. **No password reset** (T23) — a forgotten password is SSH plus a script — and
   no outbound mail sender at all. T20 shipped to Slack precisely to stop
   waiting for one.
3. **Nothing records whether writing to a contact is lawful** (T36). One
   migration; the failure mode is a fine plus a burned first impression.

---

## Backlog

One task at a time, each independently shippable: model → migration → endpoint → test → UI → merged.
Priorities: **P0** not a CRM without it · **P1** daily friction · **P2** expected but deferrable.

### A — Compliance and the model's last holes

- [ ] **T36 · P0 · Contact channel compliance — may I write to this person at all?**
      Nothing in the model records whether an *unsolicited* electronic approach to a given contact is lawful. Austria's §174 TKG 2021 bans unsolicited email and calls for direct marketing without prior consent, and it covers **legal entities too** — `office@firma.at` is not a free target — with a public-register (ECG list) check on top. The fine is real, and the mistake is invisible: nothing in a normal CRM stops you, and you only find out afterwards.
      *Scope:* on `Contact` (and `Organization`, which is where a switchboard address lives):
      · `first_contact_basis` enum — `postal_or_in_person_only` (default, the safe assumption) / `public_tender` (they invited offers) / `consent_given` / `existing_relationship` (§174(4): address obtained during a sale, own similar goods, opt-out was offered).
      · `consent_since` (date, nullable) and `consent_source` (short text — where it came from, because "we have consent" without provenance is not a defence).
      · Optional `do_not_contact` hard flag that overrides everything.
      *Done when:* the value is visible **at the point of action, not buried in a detail tab** — the compose/`mailto:` affordance (T21) is disabled with the reason shown when the basis is `postal_or_in_person_only`, and the contact list shows the state as a chip. A field nobody sees at the moment of writing prevents nothing.
      *Deliberately not automated:* no ECG-list lookup, no legal advice in the app. This records a judgement the operator made; it does not make it.
      *Why it earns P0:* it is the one feature a general-purpose CRM does not have, and the failure mode it prevents is a fine plus a burned first impression with exactly the partner you wanted.
      *Cheap now:* T17 shipped on its own, so this is a second `ALTER TABLE` on `contacts` rather than a rider on the first. Closed sets follow the T13/T17 pattern — `String` columns constrained by Pydantic `Literal`s, so adding a value never becomes an `ALTER TYPE`.
      *Related:* T21 (the send path it gates), T33 (GDPR mechanics — adjacent, not the same thing: T33 is about data subjects' rights, this is about permission to send).

- [ ] **T38 · P1 · Public tenders as a deal flavour**
      Vergabe opportunities (`ausschreibung`) do not fit the plain deal shape: they have a hard deadline, a procedure type, and a go/no-go that depends on whether the operator can bid alone. T40 already feeds these in — a tender-portal sweep creates a **plain deal** today, and the tender fields have nowhere to go.
      *Scope — extra columns on `Deal`, not a parallel entity:* `deal_kind` (`direct` / `tender`), `contracting_authority` (FK to organization — reuse the existing entity, do not re-type the buyer), `cpv_type` (service / supply / labour leasing), `procedure`, `submission_deadline`, `sme_suitable`, `consortium_allowed` (ARGE), `multi_role`, and the decision pair `fit` (`solo` / `consortium_only` / `no`) + `fit_reason` (one sentence, required when `fit` is set — a verdict without a reason is unusable three months later).
      *Rationale for folding into `Deal`:* a tender is an opportunity with a deadline and a bid/no-bid gate. A second entity would duplicate the pipeline, the contact links, the document links and the whole UI, and then need merging when a tender turns into an actual engagement. `deal_kind` plus a conditional form section costs one column.
      **`submission_deadline` must reach the morning briefing.** `app/briefing.py` exists and has no section for it; a missed tender deadline is the single most expensive thing this app can fail to do. One query and one section — do not ship the columns without it.
      *Links:* contacts and the buyer via the existing deal FKs, the PDFs via the document attachments. *Unblocked:* the dependencies (deals, attachments, watches) all shipped.

- [ ] **T37 · P2 · Direction on interactions**
      `Interaction` records kind, subject, notes and time, but not who started it — so "I wrote three times and heard nothing" and "they keep asking" look identical in the log, and no follow-up rule can be built on it.
      *Scope:* `direction` enum (`outbound` / `inbound` / `internal`, default `outbound` for the existing rows — every logged touchpoint so far was one the operator made), shown as an arrow in the timeline, filterable.
      *Cheap:* one nullable column, one migration, no new entity. The rest of the activity log already exists.
      *Feeds:* T15 (timeline), T28 (dashboard: "contacts awaiting a reply").

### B — Make the data reachable

- [ ] **T15 · P1 · Unified timeline on contact detail**
      Contact detail shows interactions only. Merge interactions, tasks, deals, documents and field changes into one reverse-chronological history — the view that answers "where are we with this person?". Becomes the app's main screen.
      *Unblocked:* every link it has to merge now exists — tasks carry contact / deal / interaction FKs, and documents and interactions attach to any record. Field changes need T29; ship the timeline without them rather than waiting.
      *Pairs with:* T37, which is what makes a run of unanswered outbound messages visible as a run.

- [ ] **T18 · P0 · One search across everything**
      Search is per-panel and matches exactly one column each — a contact is unfindable by email, phone or note text. Postgres full-text (`tsvector` + GIN, or `pg_trgm` for fuzzy names).
      *Done when:* a single search box in the app bar returns contacts, organizations, interactions, tasks, deals, documents and watches.
      *Now safe to do:* the model has settled — nine tables, no entity work pending except T36's and T38's columns.

- [ ] **T19 · P0 · Import and export**
      No way to get data in or out except by typing. CSV import with column mapping and a dry-run preview, CSV export per entity, vCard in/out for contacts. Also the GDPR data-portability answer and the escape hatch that makes a self-hosted CRM safe to adopt.
      *Note:* contacts now have 30-odd columns including a closed-set status, type and source. The importer needs a mapping UI that can say "this column is unmappable" rather than guessing, and must reject unknown enum values the way the filters do.

- [ ] **T21 · P1 · Log an email without syncing mailboxes**
      Full IMAP sync stays out of scope. The 80%: `mailto:` links from a contact, a "log this email" form, and a BCC-to-inbox address that files a message as an interaction.
      *Gated by:* T36 — the `mailto:` affordance is where channel compliance has to bite, or the field is decoration.
      *Pairs with:* T37 — a logged email is the archetypal `outbound` interaction.

- [ ] **T22 · P1 · Calendar view and `.ics` feed**
      Interactions already carry `occurred_at` and `duration_minutes`, so a month/week view is mostly presentation. A read-only iCalendar feed gets planned meetings into the calendar the operator already uses, at a fraction of the cost of real sync.
      *Auth note:* a subscribed feed cannot carry a bearer token, so this needs a per-user feed token — design it alongside T24 rather than after.

### C — Accounts

- [ ] **T23 · P0 · Password reset**
      A forgotten password today means SSH plus a Python script. fastapi-users already ships the reset and verify routers — they are simply not mounted, and no mail sender is wired up.
      *Inherits nothing from the briefing:* that shipped to a Slack webhook, and a reset link has to reach the person's mailbox rather than a channel. **The sender is this task's to build**, and it is the real cost: a from-address, SPF/DKIM, and a deliverability problem. Once it exists, T22's feed invite and any future notification have a channel.

- [ ] **T24 · P1 · Short-lived tokens with refresh, and a real logout**
      `jwt_lifetime_seconds` is 270 days with no refresh token and no denylist. A leaked token stays valid until it expires; changing the password does not invalidate it; logout only clears client storage.
      *Done when:* short access token + refresh token, revoked on password change and on explicit sign-out.

- [ ] **T34 · P1 · Rate-limit login (layer 2: durable per-account backoff)**
      The shipped throttle counts per source address, which an attacker rotating IPs walks straight through, and its window resets on every redeploy. Add `failed_login_count` and `locked_until` to the user table (Postgres, no new infrastructure) so the budget follows the *account* and survives restarts.
      *Use exponential backoff* (`locked_until = now + 2^n` seconds, capped around 15 min), not a hard lock — a hard lock hands an attacker a way to lock the operator out of their own CRM on purpose.
      *Needs:* an Alembic migration on `user`.

- [ ] **T25 · P2 · User administration in the app**
      Teams stay out of scope, but every row is already `user_id`-scoped, so a second account is a UI problem, not a data-model one. At minimum: create and deactivate users without a shell.
      *Blocks a second real user:* the briefing posts every user's message to one webhook, so a destination per user has to land with this.

### D — Polish

- [ ] **T41 · P2 · Priority visible at a glance in the task list**
      `_TaskTile` renders priority as the grey line `Priority: Low|Med|High` ([dashboard_page.dart:690](frontend/lib/pages/dashboard_page.dart#L690)), fourth in a stack of grey subtitle rows — so scanning the panel for what matters means reading every tile. Priority 0–2 already exists on the model and the form; only the presentation is missing.
      *Scope:* a colour-coded indicator on each task tile — a leading priority bar or a small chip — plus the same treatment wherever tasks are listed ([linked_tasks_section.dart](frontend/lib/widgets/linked_tasks_section.dart) on contact and deal detail, not just the dashboard). One shared widget and one `priorityColor(int)` helper, so the surfaces cannot drift apart.
      *Load-bearing detail:* **red is already taken.** An overdue task colours its title and due date with `colorScheme.error`; a red high-priority chip beside it makes the two states indistinguishable, and an overdue low-priority task would read as urgent. Pick a palette that reads against both — and keep the text label, since colour alone fails for colour-blind users and in a screenshot printed in grey.
      *Done when:* a high-priority task is identifiable without reading its subtitle, and an overdue one is still distinguishable from a high-priority one.
      *Pairs with:* T30 — sorting a list by priority is the other half of the same question.

- [ ] **T28 · P2 · Numbers on the dashboard**
      The dashboard lists records but reports nothing. A small strip: open pipeline value by stage, deals won this quarter, interactions logged this week, contacts untouched for 90 days, overdue count.
      *Cheap now:* `Deal.expected_value` is a stored generated column, so the pipeline total is one `SUM`. **Open-ended deals count separately** — sum what has an `expected_value`, then show "+ n open-ended" beside it. Never fold them in as zero; the column is NULL rather than 0 exactly so this cannot happen by accident.
      *Better with:* T37 ("contacts awaiting a reply" needs direction).

- [ ] **T30 · P2 · Filter by tag, status and date range**
      Tags are stored on every entity and cannot be filtered by anywhere. Also: sort lists by name, last contact, due date and priority.

- [ ] **T31 · P2 · Index the search columns**
      Every list endpoint does `ILIKE '%term%'` against a single unindexed column — a sequential scan per debounced keystroke. Superseded for search itself by T18, but the ordering and filter columns still want indexes: `contacts.source` / `country` / `works_with_freelancers`, `tasks.contact_id` group, `watches.next_due_at` is already indexed.

- [ ] **T26 · P2 · Archive instead of delete**
      All deletes are hard. Links are `SET NULL` everywhere, so history survives — but it survives *anonymised*: a past interaction that referenced a deleted contact now references nobody. `deleted_at` plus default filtering preserves the trail and makes an accidental delete recoverable.
      *Complicates:* T33's erase path — an archive is not an erasure, and the GDPR answer has to distinguish them.

- [ ] **T27 · P2 · Duplicate detection and merge**
      Nothing prevents entering the same person twice, and CSV import (T19) makes it routine. Warn on matching email or fuzzy name at create time; merge re-points interactions, tasks, deals, documents and watch links.
      *Do after T19*, which is what makes duplicates common enough to be worth solving.

- [ ] **T29 · P2 · Change history**
      Only `updated_at` is kept, and concurrent edits silently last-write-win. An append-only audit table gives "who changed this and when" and supports optimistic-concurrency checks on PATCH.
      *Feeds:* T15's field-change entries — the one part of the timeline that cannot be built today.

- [ ] **T32 · P2 · Error tracking and metrics**
      JSON logs and `/health` exist; nothing reports a 500 without someone reading the log. Add an error tracker and request/latency metrics.
      *Same gap, different layer:* a failed backup run is also silent (`BACKUP.md`), and a failed briefing CronJob is only visible in `kubectl get jobs`. One alerting path could cover all three.

- [ ] **T33 · P2 · GDPR mechanics**
      Personal data on named individuals in the EU implies an export-everything endpoint, a real erase path (which T26 complicates), and a documented retention period. Mostly satisfied by T19 + T26, plus writing down where it is recorded.

---

## Suggested order

Dependency- and leverage-ordered, not a strict ranking. The model is settled;
what is missing now is *reach* — getting data in, out and findable — plus two
things that are cheap and prevent expensive mistakes.

1. **T36** — one `ALTER TABLE` on `contacts`, no dependencies, and it is the
   only item here whose failure mode is a fine. It has been deferred once
   already because it rode along with T17; do not let it ride along again.
2. **T38** — the tender columns, *including the briefing section*. T40 is
   already producing tender-portal finds that land as plain deals, so every
   sweep between now and this task loses the deadline. One migration, one query,
   one form section.
3. **T15** — the unified timeline. Everything it merges now exists, and it is
   the screen that makes the last five tasks' worth of links pay off. Ship it
   without field changes rather than waiting for T29.
4. **T18** — one search. Do it before the data volume makes the per-panel
   `ILIKE` boxes actively misleading, and it subsumes half of T31.
5. **T19** — import and export. The escape hatch, the GDPR portability answer,
   and the only way to load real data without typing it. Bigger than it looks
   now that contacts have closed-set columns.
6. **T23** — password reset, which means building the mail sender. Real work,
   and nothing else can substitute for it: a reset link has to reach a mailbox.
   Once it exists, T21 and T22 get cheaper.
7. **T21 → T22** — email logging (gated by T36) and the calendar feed. Design
   T22's feed token together with **T24**, since both are auth surface.
8. **T24 + T34** — token lifetime and per-account backoff, the two remaining
   auth gaps. Neither is urgent for one operator on an unpublished instance;
   both are one evening each.

**Cheap afternoons, slot in anywhere:** T37 (one column), T41 (one widget),
T28 (one `SUM`, now that `expected_value` is generated), T31 (indexes).

**Deferred on purpose:** T25 until there is a second user, T26/T27/T29/T33
until T19 makes duplicates and portability real, T32 until something has gone
wrong quietly enough to matter.

## Guiding Principles

- **One feature at a time, fully vertical.** Model → migration → endpoint → test → UI → merged → deployed.
- **A tiny deployed app beats an elaborate localhost prototype.**
- **Resist scope creep.** If it is not on the backlog above, it goes in `IDEAS.md`, not the sprint.
- **A silent failure is worse than a loud one.** Every deferred item above that
  is really an alerting gap (backup, briefing, 500s) is tracked in T32.
