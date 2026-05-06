cd backend
.venv/bin/uvicorn app.main:app --reload
# --reload watches files and restarts on save — essential for development


## Dev — just postgres
podman-compose up -d

cd backend
.venv/bin/uvicorn app.main:app --reload
# --reload watches files and restarts on save — essential for development

cd frontend
flutter run

## Full stack (test)
podman-compose -f compose.full.yml up -d

podman-compose -f compose.full.yml build frontend && \
  podman-compose -f compose.full.yml build backend && \
  podman-compose -f compose.full.yml up -d --force-recreate frontend backend

podman-compose -f compose.full.yml logs -f backend   # watch startup + migrations


## Flutter Setup

# 1. Download and extract
mkdir -p ~/development
curl -L https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.41.9-stable.tar.xz \
  | tar xJ -C ~/development

# 2. Add to PATH (for bash — swap .bashrc for .zshrc if you use zsh)
echo 'export PATH="$HOME/development/flutter/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 3. Enable web target + install dependencies
flutter config --enable-web
flutter doctor

# 4. Chromium for Flutter web dev (Flutter can't use Firefox)
sudo dnf install chromium

echo 'export CHROME_EXECUTABLE=chromium-browser' >> ~/.bashrc
source ~/.bashrc
flutter doctor

## Git Stuff

```
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