# tinyCRM

## Local Development

### Backend

Run the backend locally
```bash
cd backend
.venv/bin/uvicorn app.main:app --reload
```

Apply schema migrations via alembic locall
```bash
cd backend 
.venv/bin/alembic upgrade head
```

Run the database server
```bash
podman-compose up -d
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

## Flutter Setup

# 1. Download and extract
```bash
mkdir -p ~/development
curl -L https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.41.9-stable.tar.xz \
  | tar xJ -C ~/development
```

# 2. Add to PATH (for bash — swap .bashrc for .zshrc if you use zsh)
```bash
echo 'export PATH="$HOME/development/flutter/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

# 3. Enable web target + install dependencies
```bash
flutter config --enable-web
flutter doctor
```

# 4. Chromium for Flutter web dev (Flutter can't use Firefox)
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