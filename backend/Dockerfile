# Two stages so the tools that build the environment stay out of the image that
# runs it: uv (and the Rust crates compiled into it) and the base image's pip
# (with its vendored setuptools, msgpack and urllib3) are needed to install, never
# to serve — and every one of them is something the image scan in ci.yml would
# otherwise have to keep clean.
FROM docker.io/library/python:3.14-slim@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4 AS build

# uv handles dependency management; copy its static binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.11.25@sha256:1e3808aa9023d0980e7c15b1fa7c1ac16ff35925780cf5c459858b2d693f01a9 /uv /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Install locked dependencies first. This layer is cached unless the lockfile
# or pyproject changes, so app-code edits don't re-resolve the environment.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM docker.io/library/python:3.14-slim@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4

# Debian security updates land in the archive days before the python image is
# rebuilt on top of them, so take them here rather than wait.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes --root-user-action=ignore pip

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

# Same path as in the build stage: the venv's scripts and its python symlink
# point at absolute paths, and the interpreter they point at is the same one.
COPY --from=build /app/.venv /app/.venv

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY scripts/ scripts/
COPY log_config.json .

# Version metadata. Kept late so the layers above stay cached across builds.
# GIT_COMMIT and APP_VERSION are passed in (git isn't available here); the
# build timestamp is recorded now so it reflects this exact image.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
RUN date -u +"%Y-%m-%dT%H:%M:%SZ" > /app/build_timestamp.txt

EXPOSE 8000

# Serve only. `.venv/bin` is on PATH, so uvicorn resolves to the locked
# environment.
#
# Migrations deliberately do not run here. Under a rolling update, or with more
# than one replica, every starting pod would race the same `alembic upgrade
# head`. The Helm chart runs it once per release instead, as a pre-upgrade hook
# Job that must succeed before the new pods start
# (charts/tinycrm/templates/migrate-job.yaml). The image still carries alembic,
# which is what that Job runs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-config log_config.json"]
