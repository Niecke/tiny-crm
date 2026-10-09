"""The job queue itself (app/jobs/): its schema, its housekeeping, its logs.

What a particular job does is tested next to the feature it belongs to — the
reset mail in test_password_reset.py. The worker process is test_worker.py.
"""

import asyncio
import json
import logging
import pkgutil
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import typer
from procrastinate.schema import SchemaManager
from procrastinate.testing import InMemoryConnector

import app.jobs
from app import cli
from app.jobs import (
    DEFAULT_QUEUE,
    MAIL_QUEUE,
    database_dsn,
    jobs_app,
    ping,
    remove_old_jobs,
    retry_stalled_jobs,
)
from app.logging_config import JsonFormatter

RunJobs = Callable[[], Awaitable[None]]

VENDORED = Path(__file__).resolve().parent.parent / "alembic" / "procrastinate"


def _version(path: Path) -> tuple[int, ...]:
    match = re.fullmatch(r"schema_(\d+(?:\.\d+)*)\.sql", path.name)
    assert match, f"unexpected file name {path.name}"
    return tuple(int(part) for part in match.group(1).split("."))


def test_the_vendored_schema_is_the_installed_procrastinate_s() -> None:
    """procrastinate was updated and its schema changed with it.

    The tables are created by an Alembic revision from the SQL vendored in
    alembic/procrastinate/, so a new schema needs a new revision before the
    new library runs against the old tables. The README there has the steps.
    """
    newest = max(VENDORED.glob("schema_*.sql"), key=_version)

    assert newest.read_text(encoding="utf-8") == SchemaManager.get_schema(), (
        f"{newest.name} is not the schema of the installed procrastinate — "
        "see alembic/procrastinate/README.md"
    )


def test_the_queue_uses_the_application_database() -> None:
    dsn = database_dsn("postgresql+asyncpg://crm:s3cr3t@db.internal:5432/crm")

    assert dsn == "postgresql://crm:s3cr3t@db.internal:5432/crm"


def test_the_worker_imports_every_job_module() -> None:
    """A job whose module the worker never imported fails as "task not found"."""
    modules = {
        f"{app.jobs.__name__}.{module.name}" for module in pkgutil.iter_modules(app.jobs.__path__)
    }

    assert modules == set(jobs_app.import_paths)


async def test_a_ping_is_answered_on_every_queue(
    run_jobs: RunJobs, job_queue: InMemoryConnector
) -> None:
    await ping.defer_async()
    await ping.configure(queue=MAIL_QUEUE).defer_async()

    await run_jobs()

    assert [(job["queue_name"], job["status"]) for job in job_queue.jobs.values()] == [
        (DEFAULT_QUEUE, "succeeded"),
        (MAIL_QUEUE, "succeeded"),
    ]


# The operator's check, `python -m app.cli ping-worker`.


async def test_ping_worker_reports_each_queue(
    run_jobs: RunJobs, capsys: pytest.CaptureFixture[str]
) -> None:
    waiting = asyncio.create_task(cli._ping_worker([MAIL_QUEUE, DEFAULT_QUEUE], timeout=5))
    await asyncio.sleep(0.05)
    await run_jobs()
    await waiting

    out = capsys.readouterr().out
    assert "mail: answered after" in out
    assert "default: answered after" in out


async def test_ping_worker_fails_when_nothing_takes_the_job(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(typer.Exit) as raised:
        await cli._ping_worker([MAIL_QUEUE], timeout=0.3)

    assert raised.value.exit_code == 1
    assert "no worker took a job from mail" in capsys.readouterr().err


# Housekeeping.


def test_housekeeping_is_scheduled_on_the_default_queue() -> None:
    scheduled = {
        periodic.task.name: (periodic.cron, periodic.task.queue)
        for periodic in jobs_app.periodic_registry.periodic_tasks.values()
    }

    assert scheduled == {
        "retry_stalled_jobs": ("*/5 * * * *", DEFAULT_QUEUE),
        "remove_old_jobs": ("17 3 * * *", DEFAULT_QUEUE),
    }


async def test_a_dead_worker_s_job_is_handed_out_again(
    run_jobs: RunJobs, job_queue: InMemoryConnector, caplog: pytest.LogCaptureFixture
) -> None:
    await ping.defer_async()
    await ping.defer_async()
    abandoned, running = job_queue.jobs[1], job_queue.jobs[2]
    # Worker 98 is alive and busy; worker 99 was killed minutes ago, mid-job.
    job_queue.workers[98] = datetime.now(UTC)
    job_queue.workers[99] = datetime.now(UTC) - timedelta(minutes=5)
    abandoned.update(status="doing", worker_id=99)
    running.update(status="doing", worker_id=98)

    await retry_stalled_jobs.configure(task_kwargs={"timestamp": 0}).defer_async()
    await run_jobs()

    # Queued again, and then simply run by the worker that found it.
    assert abandoned["status"] == "succeeded"
    assert running["status"] == "doing"
    assert "Job 1 (ping) was left behind by a dead worker" in caplog.text


async def test_old_jobs_are_removed_and_failures_kept_longer(
    run_jobs: RunJobs, job_queue: InMemoryConnector
) -> None:
    ages = {
        "succeeded last week": ("succeeded", timedelta(days=8)),
        "succeeded yesterday": ("succeeded", timedelta(days=1)),
        "failed last week": ("failed", timedelta(days=8)),
        "failed last month": ("failed", timedelta(days=31)),
    }
    ids: dict[str, int] = {}
    for label, (status, age) in ages.items():
        job_id = await ping.defer_async()
        ids[label] = job_id
        job_queue.jobs[job_id]["status"] = status
        for event in job_queue.events[job_id]:
            event["at"] = datetime.now(UTC) - age

    await remove_old_jobs.configure(task_kwargs={"timestamp": 0}).defer_async()
    await run_jobs()

    kept = {label for label, job_id in ids.items() if job_id in job_queue.jobs}
    assert kept == {"succeeded yesterday", "failed last week"}


# Logs.


def _job_record(message: str) -> logging.LogRecord:
    record = logging.LogRecord(
        "procrastinate.worker", logging.INFO, __file__, 1, message, None, None
    )
    # What procrastinate attaches to every record about a job.
    record.action = "start_job"
    record.job = {
        "id": 12,
        "task_name": "send_password_reset",
        "queue": "mail",
        "attempts": 2,
        "task_kwargs": {"user_id": "5f0c", "requested_at": "2026-10-09T07:00:00+00:00"},
        "call_string": "send_password_reset[12](user_id='5f0c', requested_at='2026-…')",
    }
    return record


def test_a_job_s_log_line_names_the_job_and_leaves_out_its_arguments() -> None:
    """Arguments are ids today; the log must not depend on that staying true."""
    record = _job_record(
        "Starting job send_password_reset[12](user_id='5f0c', requested_at='2026-…')"
    )

    line = JsonFormatter().format(record)

    assert "5f0c" not in line
    logged = json.loads(line)
    assert logged["message"] == "Starting job send_password_reset[12]"
    assert logged["job_id"] == 12
    assert logged["task"] == "send_password_reset"
    assert logged["queue"] == "mail"
    assert logged["attempts"] == 2
    assert logged["action"] == "start_job"


def test_other_log_lines_are_unchanged() -> None:
    record = logging.LogRecord("app.mail", logging.INFO, __file__, 1, "Mail %r sent", ("x",), None)

    logged = json.loads(JsonFormatter().format(record))

    assert logged["message"] == "Mail 'x' sent"
    assert "job_id" not in logged and "action" not in logged
