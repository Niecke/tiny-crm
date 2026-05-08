FROM docker.io/library/python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY scripts/ scripts/

EXPOSE 8000

# Run migrations then start the server.
# alembic upgrade head is idempotent — safe to run on every startup.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
