# tinyCRM

## Local Development

### Setup Python

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

cd backend
cp .env.example .env          # then edit secrets if needed
uv sync                       # ← this is your "pip install"
```

### Run service

Run the database server and MinIO
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
uv run uvicorn app.main:app --reload--log-config log_config.json
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
  podman-compose -f compose.full.yml up -d --force-recreate frontend backend
```

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
cd backend && uv run pytest                   # 80 tests
cd backend && uv run pytest --cov=app         # with a coverage summary

cd frontend && flutter test                   # widget_test.dart is browser-only, skipped here
cd frontend && flutter test --platform chrome # includes the widget test
```

`TEST_DATABASE_URL` defaults to `postgresql+asyncpg://crm:crm@localhost:5432/postgres`. The
database it names is only used to issue `CREATE DATABASE`, never written to.

What the backend suite covers: cross-user isolation for all five owned resources (read,
change, delete, list, and anonymous access — table-driven in
`tests/test_cross_user_isolation.py`, add a row when a router is added), CRUD round-trips
and validation per router, the login and password-change flows, and the pure helpers.
S3 is faked in memory for the document tests; the real MinIO round-trip is `ci/smoke.sh`.

## CI/CD

Work happens on `dev`; `main` is what ships. Two workflows:

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
4. **Integration test** — starts those exact images with Postgres and MinIO from
   `compose.ci.yml` and runs `ci/smoke.sh`: health, matching versions across both images,
   the Flutter bundle and its SPA fallback, admin creation, login, a 401 for anonymous
   requests, a contact round-trip through Postgres and a document round-trip through MinIO.
   The backend runs with `ENVIRONMENT=production` and generated secrets, so the run also
   proves the production startup guard passes on a properly configured instance.

Only `pull_request` triggers it. While a PR is open, every push to `dev` fires
`synchronize` on the same commit, so adding a `push: dev` trigger would just run the whole
pipeline twice per commit. Open the PR as a **draft** when work starts and dev commits are
covered from the first push. `workflow_dispatch` runs the two test jobs on demand (a manual
run has no PR head to tag images with, so it stops there).

**`.github/workflows/promote.yml`** — on merge to `main`, resolves the merged PR's head sha
and re-tags the already-tested images with `<short-main-sha>` and `latest` via
`docker buildx imagetools create`. Nothing is rebuilt, so the digest that passed the
integration test is the digest that deploys.

Required once, in GitHub → Settings → Branches → `main`: require the checks
`Backend tests`, `Frontend tests`, `Build backend`, `Build frontend`, `Integration test`,
and disallow direct pushes — a commit that never went through a PR has no image to promote.

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
