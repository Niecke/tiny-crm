# tinyCRM

A single-operator CRM for self-employment: contacts, organizations, deals,
tasks, interactions, projects, documents and a watch list of sources to sweep.

- **[FEATURES.md](FEATURES.md)** — what it does, the API surface, and the rules
  worth knowing before changing anything.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — goals, scope, and how work is tracked.
- **[GitHub Issues](https://github.com/Niecke/tiny-crm/issues)** — what is still open, and in what order.
- **[deploy/README.md](deploy/README.md)** — how it reaches the cluster.

This file is the how-to-run-it half.

## Local Development

### Setup Python

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

cd backend
cp .env.example .env          # then edit secrets if needed
uv sync                       # ← this is your "pip install"
```

### Run service

Run the database server and the local S3 fixture (Versity Gateway)
```bash
podman-compose up -d
```

Apply schema migrations via alembic locall
```bash
cd backend 
uv run alembic upgrade head
```

Create new alembic migration
```bash
uv run alembic revision --autogenerate -m "add phone to contacts"
```

Run the backend locally
```bash
cd backend
uv run uvicorn app.main:app --reload --log-config log_config.json
```

Run flutter in debug mode locally
```bash
cd frontend
flutter run
```

## Full stack (test)
Containers are build each time to get latest code changes.

```bash
podman-compose -f compose.full.yml build frontend && \
  podman-compose -f compose.full.yml build backend && \
  podman-compose -f compose.full.yml build migrate && \
  podman-compose -f compose.full.yml up -d --force-recreate frontend backend
```

The `migrate` service runs `alembic upgrade head` once and exits; `backend`
waits for it to succeed. Migrations no longer run from the backend image's
`CMD` — under a rolling update every starting replica would race the same
migration — so the Helm chart runs them as a pre-upgrade hook and compose runs
them as this one-shot service.

Shutdown again
```bash
podman-compose -f compose.full.yml down
```

## Flutter Setup

### 1. Download and extract
```bash
mkdir -p ~/development
curl -L https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.41.9-stable.tar.xz \
  | tar xJ -C ~/development
```

### 2. Add to PATH (for bash — swap .bashrc for .zshrc if you use zsh)
```bash
echo 'export PATH="$HOME/development/flutter/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 3. Enable web target + install dependencies
```bash
flutter config --enable-web
flutter doctor
```

### 4. Chromium for Flutter web dev (Flutter can't use Firefox)
```bash
sudo dnf install chromium

echo 'export CHROME_EXECUTABLE=chromium-browser' >> ~/.bashrc
source ~/.bashrc
flutter doctor
```

## Git Stuff

```bash
#!/usr/bin/env bash
set -e

echo ">>> ruff (backend)"
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
cd ..

echo ">>> flutter analyze (frontend)"
"$HOME/development/flutter/bin/flutter" analyze frontend
```
## Tests

The backend suite needs a Postgres to talk to — it creates a scratch database per run and
drops it afterwards, so the local compose stack is enough. Unit tests (config guard, login
throttle, upload guards) run without one; everything that touches a router does not.

```bash
podman-compose up -d db                       # or point TEST_DATABASE_URL elsewhere
cd backend && uv run pytest                   # 340 tests
cd backend && uv run pytest --cov=app         # with a coverage summary

cd frontend && flutter test                   # widget_test.dart is browser-only, skipped here
cd frontend && flutter test --platform chrome # includes the widget test
```

`TEST_DATABASE_URL` defaults to `postgresql+asyncpg://crm:crm@localhost:5432/postgres`. The
database it names is only used to issue `CREATE DATABASE`, never written to.

What the backend suite covers: cross-user isolation for every owned resource (read,
change, delete, list, and anonymous access — table-driven in
`tests/test_cross_user_isolation.py`, add a row when a router is added), CRUD round-trips
and validation per router, the deal pricing and stage rules, task recurrence, the watch
sweep and its cadence, the briefing windows, the login and password-change flows, and the
pure helpers. S3 is faked in memory for the document tests; the real S3 round-trip is
`ci/smoke.sh`. `uv run mypy app tests` must also be clean — it is a CI gate.

## The morning briefing

Overdue tasks, today's plan, the sources due to be swept and the people still
waiting to be written to, posted to Slack on weekday mornings — the same
information the dashboard's "Upcoming" panel holds, pushed, so it is visible
without an open browser tab. A waiting capture is the one thing here with no due
date and no other way to resurface, which is why it is in the message at all.

`backend/app/briefing.py` gathers and renders it; `scripts/send_briefing.py`
runs it. There is no endpoint and no scheduler inside the API: a loop in the
API would fire once per replica, and a delivery that quietly stops looks
exactly like a quiet week. In the cluster it is a CronJob
(`charts/tinycrm/templates/briefing-cronjob.yaml`) running the backend image,
so a failed briefing is a failed Job.

```bash
cd backend
uv run python scripts/send_briefing.py --dry-run   # print it, send nothing
uv run python scripts/send_briefing.py             # needs SLACK_WEBHOOK_URL
```

Three settings, all in `.env.example`: `SLACK_WEBHOOK_URL` (Slack → Apps →
Incoming Webhooks; without it a real send exits 2 rather than doing nothing),
`BRIEFING_TIMEZONE` and `APP_URL` for the link in the message.

**`BRIEFING_TIMEZONE` is not cosmetic.** The task form files a due date as
23:59 local, which is 21:59Z in summer — so a briefing that computed "today"
in UTC would put a task due tonight in tomorrow's message. The day boundary is
the operator's, and the window is 23 or 25 hours long across a DST switch.

One webhook, one channel, so every user's briefing lands in the same place.
That is the single-operator shape this app is built for; a second real user
needs a destination per user first.

## CI/CD

Work happens on `feat/*` branches; `main` is what ships. The pipeline workflows:

**`.github/workflows/ci.yml`** — on a pull request into `main`:

1. **Backend tests** (`ruff check`, `ruff format --check`, `pytest` against a Postgres service
   container) and **Frontend tests** (`flutter analyze`, `flutter test`, run in the same
   Flutter image digest the frontend Dockerfile builds with). Both upload their JUnit/JSON
   report and coverage file.
2. **Test report** — renders both suites into one table (passed/failed/skipped, line
   coverage, duration) via `ci/pr_report.py`, writes it to the job summary and keeps a single
   updated comment on the PR, so results are readable without opening the run. Runs even when
   a suite failed, and lists the failing test names.
3. **Build backend** / **Build frontend** — only if both test jobs pass. Images are pushed
   as `ci-<short-sha-of-the-PR-head>`; the PR head sha, not the ephemeral merge commit, is
   also baked in as `GIT_COMMIT`.
4. **Integration test** — starts those exact images with Postgres and the S3 fixture from
   `compose.ci.yml` and runs `ci/smoke.sh`: health, matching versions across both images,
   the Flutter bundle and its SPA fallback, admin creation, login, a 401 for anonymous
   requests, a contact round-trip through Postgres and a document round-trip through S3.
   The backend runs with `ENVIRONMENT=production` and generated secrets, so the run also
   proves the production startup guard passes on a properly configured instance.

Only `pull_request` triggers it. While a PR is open, every push to `dev` fires
`synchronize` on the same commit, so adding a `push: dev` trigger would just run the whole
pipeline twice per commit. Open the PR as a **draft** when work starts and dev commits are
covered from the first push. `workflow_dispatch` runs the two test jobs on demand (a manual
run has no PR head to tag images with, so it stops there).

**`.github/workflows/promote.yml`** — on merge to `main`, resolves the merged PR's head sha
and re-tags the already-tested images with `sha-<short-main-sha>` via
`docker buildx imagetools create`. Nothing is rebuilt, so the digest that passed the
integration test is the digest that deploys.

### Versions and releases

Pull requests merge as **squashes**, and the **pull request title** is the commit that
lands on `main`. It must be a [conventional commit](https://www.conventionalcommits.org/)
— `.github/workflows/commitlint.yml` checks it on every title edit:

| Pull request title | Release | `1.4.2` becomes |
|---|---|---|
| `fix: promote skips missing backup image` | patch | `1.4.3` |
| `feat: morning briefing cronjob` | minor | `1.5.0` |
| `feat!: drop the v1 contacts endpoint` | major | `2.0.0` |
| `chore(deps): bump postgres digest` | none | `1.4.2` |
| `docs: rewrite the deploy README` | none | `1.4.2` |

Allowed types: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`,
`revert`, `style`, `test`. Renovate's `chore(deps):` / `fix(deps):` titles already fit.
Anything that ships inside an image — the Dockerfile base images, the backend's
`[project] dependencies`, pubspec `dependencies` — is `fix(deps)` and cuts a patch release;
CI actions, compose files and dev dependencies stay `chore(deps)` and do not.

**`.github/workflows/release-please.yml`** keeps one release pull request open against
`main`. It bumps a single version for the whole product — `version.txt`,
`backend/pyproject.toml` and `uv.lock`, `frontend/pubspec.yaml`, and both `version` and
`appVersion` in `charts/tinycrm/Chart.yaml` — and prepends the changes to `CHANGELOG.md`.
Merging it tags `vX.Y.Z` and publishes the GitHub Release. Never bump those versions by
hand; the files are listed in `release-please-config.json`.

`main` is protected by the `protect_main` ruleset, kept in
[`.github/ruleset/protect_main.json`](.github/ruleset/protect_main.json): squash merges
only, linear history, no force pushes or deletion, and every job in `ci.yml` plus
`commitlint` is a required check. Direct pushes are disallowed — a commit that never went
through a PR has no image to promote. The one bypass is deploy keys: promote pushes
its `Deploy <sha>` commit over SSH with the `DEPLOY_KEY` secret, because a personal
repository cannot exempt the GitHub Actions app from a ruleset. Adding a job to `ci.yml` means adding it to that
file, or it can go red without blocking a merge. The file is not applied automatically;
after changing it:

```bash
gh api -X PUT repos/Niecke/tiny-crm/rulesets/22081158 --input .github/ruleset/protect_main.json
```

### Running the integration test locally

```bash
# against images already in the registry
IMAGE_TAG=ci-abc1234 ci/smoke.sh

# against locally built images, next to a running dev stack
podman build --build-arg GIT_COMMIT=local -t localhost/tinycrm-ci/backend:test ./backend
podman build --build-arg GIT_COMMIT=local -t localhost/tinycrm-ci/frontend:test ./frontend
COMPOSE_CMD=podman-compose PULL_POLICY=never \
  REGISTRY=localhost/tinycrm-ci IMAGE_TAG=test EXPECTED_COMMIT=local \
  BACKEND_PORT=8100 FRONTEND_PORT=8180 ci/smoke.sh
```

The CI stack uses its own Compose project name (`tinycrm-ci`), so it does not touch the
containers from `compose.full.yml`.
