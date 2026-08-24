FROM docker.io/library/python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

# uv handles dependency management; copy its static binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

# Install locked dependencies first. This layer is cached unless the lockfile
# or pyproject changes, so app-code edits don't re-resolve the environment.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY scripts/ scripts/
COPY log_config.json .

# Version metadata. Kept late so the layers above stay cached across builds.
# GIT_COMMIT is passed in (git isn't available here); the build timestamp is
# recorded now so it reflects this exact image.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
RUN date -u +"%Y-%m-%dT%H:%M:%SZ" > /app/build_timestamp.txt

EXPOSE 8000

# Run migrations then start the server. `.venv/bin` is on PATH, so alembic and
# uvicorn resolve to the locked environment.
# alembic upgrade head is idempotent — safe to run on every startup.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-config log_config.json"]
