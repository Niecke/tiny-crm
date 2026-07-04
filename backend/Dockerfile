FROM docker.io/library/python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

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

# Run migrations then start the server.
# alembic upgrade head is idempotent — safe to run on every startup.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-config log_config.json"]
