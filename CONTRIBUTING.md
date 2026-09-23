# Working on tinyCRM

A small CRM for self-employment, built as a learning project for FastAPI and Flutter.

What is already built is documented in [FEATURES.md](FEATURES.md). What is still
open lives in [GitHub Issues](https://github.com/Niecke/tiny-crm/issues) — this
file is the standing context that does not belong in any single issue.

## Goals

- Track contacts, organizations, interactions, tasks and deals for a solo business.
- Learn FastAPI (backend) and Flutter web (frontend) end-to-end.
- Ship a real, deployed, authenticated app — not just a localhost demo.

## Deliberately out of scope

- Marketing automation
- Teams, roles, per-record permissions (rows are `user_id`-scoped, but there is one operator)
- Lead scoring, territories, workflow builders
- Built-in invoicing and time tracking (separate concern)
- Full mailbox sync (IMAP/Graph) — the cheap 80% is tracked instead
- Crawling or scraping any watched source (the watch list is a habit, not a scraper)

## Guiding principles

- **One feature at a time, fully vertical.** Model → migration → endpoint → test → UI → merged → deployed.
- **A tiny deployed app beats an elaborate localhost prototype.**
- **Resist scope creep.** If it is not an issue, it is not the sprint.
- **A silent failure is worse than a loud one.** Every deferred alerting gap — backup, briefing, 500s — is tracked together, not separately forgotten.

## How work is tracked

Everything open is a GitHub issue. There is no backlog file; a task that exists
in two places drifts in one of them.

**Priority labels** — `P0` not a CRM without it · `P1` daily friction · `P2`
expected but deferrable.

**Area labels** — `backend`, `frontend`, `infra`, `docs`, `security`.

**Tracking issues** carry the section-level ordering and dependencies that used
to live in the plan's "suggested order":

| | |
|---|---|
| A — Compliance and the model's last holes | #145 |
| B — Make the data reachable | #146 |
| C — Accounts and auth | #147 |
| D — Polish | #148 |
| E — Deal velocity | #149 |

**Milestones** — `React parity` holds the frontend rewrite and every screen that
must exist before the cutover.

**Design documents** stay in the repo when a spec is too long to read in an
issue body: [DASHBOARD.md](DASHBOARD.md) is the metric catalogue for #138. The
issue is the work; the document is the detail.

Historical task IDs (`T15`, `T36`, …) are kept in issue titles so older commit
messages and code comments still resolve.

## Stack (as built)

| Layer | Actual | Notes |
|---|---|---|
| API | FastAPI + uvicorn, SQLAlchemy 2.0 async, Pydantic v2, Alembic | JSON logging via `log_config.json` |
| Database | PostgreSQL 18 + asyncpg | Tags use Postgres-native `ARRAY(String)` |
| Auth | fastapi-users, JWT bearer, admin created via `scripts/create_admin.py` | No register / verify / reset routers mounted |
| Blob store | S3-compatible via aioboto3, MinIO locally | Bucket versioning checked at boot |
| Client | Flutter web, Riverpod 3, go_router 17, dio, flutter_secure_storage | Hand-written models; being replaced, see #122 |
| Scheduling | Kubernetes CronJobs on the backup and backend images | Off-site backup; weekday morning briefing to Slack. No scheduler inside the API |
| CI/CD | GitHub Actions → GHCR, Renovate | Test → build → integration test → promote-by-digest. Versioning is #114 |
| Deploy | Flux (pull-based), Helm chart in `charts/tinycrm/` | Merging to `main` is the deploy |
| Serving | Caddy inside the frontend image, Podman/Docker Compose | `compose.full.yml` = db + minio + backend + frontend |
