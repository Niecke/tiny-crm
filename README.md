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

```bash
cd backend && uv run pytest        # 16 tests, no database needed
cd frontend && flutter test        # widget_test.dart is browser-only and skipped here
cd frontend && flutter test --platform chrome   # includes the widget test
```

## CI/CD

Work happens on `dev`; `main` is what ships. Two workflows:

**`.github/workflows/ci.yml`** — on a pull request into `main`:

1. **Backend tests** (`ruff check`, `ruff format --check`, `pytest`) and **Frontend tests**
   (`flutter analyze`, `flutter test`, run in the same Flutter image digest the frontend
   Dockerfile builds with).
2. **Build backend** / **Build frontend** — only if both test jobs pass. Images are pushed
   as `ci-<short-sha-of-the-PR-head>`; the PR head sha, not the ephemeral merge commit, is
   also baked in as `GIT_COMMIT`.
3. **Integration test** — starts those exact images with Postgres and MinIO from
   `compose.ci.yml` and runs `ci/smoke.sh`: health, matching versions across both images,
   the Flutter bundle and its SPA fallback, admin creation, login, a 401 for anonymous
   requests, a contact round-trip through Postgres and a document round-trip through MinIO.
   The backend runs with `ENVIRONMENT=production` and generated secrets, so the run also
   proves the production startup guard passes on a properly configured instance.

Pushes to `dev` run the two test jobs only — no registry writes.

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
