# tinyCRM

A small CRM for self-employment, built as a learning project for FastAPI and Flutter.

## Goals

- Track contacts, interactions, tasks, and deals for a solo business.
- Learn FastAPI (backend) and Flutter web (frontend) end-to-end.
- Ship a real, deployed, authenticated app — not just a localhost demo.

## Tech Stack

### Backend
- **FastAPI** with `uvicorn`
- **SQLAlchemy 2.0** (async) + **Alembic** for migrations
- **Pydantic v2** for schemas
- **SQLite** for persistence (WAL mode)
- **fastapi-users** for authentication (JWT in Authorization header)
- `ruff` + `mypy` + `pytest` for quality

### Frontend
- **Flutter** (web target)
- **Riverpod** for state management
- **go_router** for routing
- **dio** for HTTP with an auth interceptor
- **freezed** for immutable models
- **flutter_secure_storage** for JWT storage

### Infrastructure
- **Hetzner CX22** VM (2 vCPU, 4 GB RAM, ~€4/month)
- **Docker** + **docker-compose**
- **Caddy** reverse proxy with automatic Let's Encrypt TLS
- **GitHub Actions** for CI/CD, images on **ghcr.io**
- SSH-based deploy from `main`

## Feature Scope

### MVP (Phases 0–3)
- Contacts (name, company, email, phone, address, tags, notes)
- Authentication (single admin user to start)
- Interactions / activity log linked to contacts
- Tasks / follow-ups with due dates
- "Today" dashboard for open and overdue tasks

### Phase 2+
- Deals / opportunities with pipeline stages (Lead → Proposal → Won/Lost)
- Kanban board view
- Full-text search via SQLite FTS5
- CSV import/export
- Document attachments (file paths, not blobs)

### Deliberately Out of Scope
- Marketing automation
- Multi-user permissions / teams
- Lead scoring, territories, workflow builders
- Built-in invoicing and time tracking (separate concern)
- Email sync (too complex for a learning MVP)

## Development Phases

### Phase 0 — Setup (½ day)
Prove the stack works end-to-end before writing any real feature.

- FastAPI project scaffold with `uvicorn` and a `/ping` endpoint
- SQLAlchemy 2.0 async connection to SQLite, Alembic initialized
- Flutter web project that calls `/ping` and displays the result
- CORS configured so Flutter web can talk to FastAPI
- Repo on GitHub, basic `ruff` + `flutter analyze` pre-commit hooks

**Exit criteria:** `curl` hits `/ping`, Flutter web shows "pong".

### Phase 1 — Contacts CRUD (3–5 days)
The classic "learn a web framework" exercise, done properly.

- `Contact` SQLAlchemy model + Alembic migration
- Pydantic schemas: `ContactCreate`, `ContactRead`, `ContactUpdate`
- REST endpoints: list (paginated), get, create, update, delete
- Flutter: list screen, detail screen, form screen
- Riverpod providers for contact state, `dio` HTTP client wrapper
- First GitHub Actions workflow: lint + test on every push

**Learning focus:** request/response lifecycle, Pydantic, FastAPI `Depends`, Flutter widget tree, Riverpod `AsyncValue`.

### Phase 2 — Authentication (2–3 days)
Added early so every later feature is built auth-aware.

- `fastapi-users` integration, JWT in `Authorization` header
- Single admin user created via CLI command (no signup flow yet)
- Protected routes via `Depends(current_active_user)`
- Flutter login screen, JWT stored in `flutter_secure_storage`
- `dio` interceptor: attach token, bounce to login on 401
- `go_router` redirect guard for unauthenticated users

**Learning focus:** password hashing, JWT lifecycle, route protection on both ends.

### Phase 3 — Interactions & Tasks (3–4 days)
Relationships and foreign keys.

- `Interaction` and `Task` models with `contact_id` FKs
- Nested endpoints: `GET /contacts/{id}/interactions`, etc.
- Tabs on the Flutter contact detail screen
- "Today" dashboard listing open and overdue tasks across all contacts

**Learning focus:** SQLAlchemy relationships, join queries, nested REST URL design.

### Phase 4 — Deals & Pipeline (3–4 days)
More complex UI and state.

- `Deal` model with stage enum, value, expected close date, contact FK
- Endpoint to update a deal's stage
- Kanban board in Flutter with drag-and-drop between stage columns
- Optimistic UI updates when moving deals

**Learning focus:** enums in Pydantic/SQLAlchemy, complex Flutter layouts, optimistic state.

### Phase 5 — Search & Import/Export (2–3 days)
- SQLite FTS5 virtual table for contacts and interaction notes
- Search endpoint and Flutter search screen
- CSV import endpoint (stdlib `csv`)
- CSV export endpoint for contacts

**Learning focus:** SQLite-specific features, file uploads in FastAPI.

### Phase 6 — Hardening & Full CI/CD (2–3 days)
- Dockerize the backend, multi-stage build including Flutter web bundle
- `docker-compose.yml` with FastAPI + Caddy
- `Caddyfile` with automatic TLS for the domain
- GitHub Actions: build image → push to ghcr.io → SSH deploy to Hetzner
- Nightly SQLite backup cron (`sqlite3 .backup`), rsynced offsite
- UFW firewall (22, 80, 443 only), SSH key-only auth
- Branch protection on `main`, deploy only on green CI

**Learning focus:** containerization, reverse proxies, deployment pipelines, ops basics.

## CI/CD Pipeline Stages

Built up alongside the phases, not all at once:

1. **Stage 1 (Phase 1):** Lint + test on every push/PR. `ruff`, `mypy`, `pytest`, `flutter analyze`, `flutter test`.
2. **Stage 2 (Phase 4):** Build Docker image, push to `ghcr.io`, tag with `latest` + git SHA.
3. **Stage 3 (Phase 6):** SSH into Hetzner VM, `docker compose pull && docker compose up -d`. Only from `main`, only after tests pass.

## Repository Layout (planned)

```
crm/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routers/
│   │   └── auth/
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── lib/
│   │   ├── main.dart
│   │   ├── features/
│   │   ├── core/
│   │   └── router.dart
│   └── pubspec.yaml
├── deploy/
│   ├── docker-compose.yml
│   └── Caddyfile
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
└── README.md
```

## Guiding Principles

- **Ship Phase 1 to a real URL before starting Phase 2.** A tiny deployed app beats an elaborate localhost prototype.
- **One feature at a time, fully vertical.** Model → migration → endpoint → test → UI → merged → deployed.
- **Auth early, not late.** Retrofitting auth is painful.
- **Resist scope creep.** If it's not in the feature list above, it goes in a `IDEAS.md`, not the sprint.
