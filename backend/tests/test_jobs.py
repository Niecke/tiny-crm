"""The job queue itself (app/jobs/): its schema, its housekeeping, its logs.

What a particular job does is tested next to the feature it belongs to — the
reset mail in test_password_reset.py. The worker process is test_worker.py.
"""

import ast
import asyncio
import json
import logging
import pkgutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import typer
from procrastinate.exceptions import ConnectorException, UniqueViolation
from procrastinate.manager import QUEUEING_LOCK_CONSTRAINT
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

REVISIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _named_by_revisions() -> dict[str, list[str]]:
    """The procrastinate migration files each Alembic revision applies, by
    revision file.

    Read from the source, not imported: a revision module only works inside a
    running migration.
    """
    named: dict[str, list[str]] = {}
    for path in sorted(REVISIONS.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "PROCRASTINATE_MIGRATIONS"
            ):
                named[path.name] = list(ast.literal_eval(node.value))
    return named


def test_every_procrastinate_migration_is_applied_by_a_revision() -> None:
    """procrastinate was updated and brought schema changes with it.

    Its tables are migrated by Alembic revisions that name the SQL files the
    package ships. A file no revision names is a change the database never
    gets, while the new library already expects it. Add a revision for the
    files listed — v2w3x4y5z6a7_procrastinate_schema.py says how.
    """
    shipped = {
        script.name
        for script in resources.files("procrastinate.sql.migrations").iterdir()
        if script.name.endswith(".sql")
    }
    applied = [name for names in _named_by_revisions().values() for name in names]

    assert sorted(shipped - set(applied)) == [], "shipped by procrastinate, applied by no revision"
    assert sorted(set(applied) - shipped) == [], "named by a revision, no longer shipped"
    assert len(applied) == len(set(applied)), "a file is applied twice"


def test_a_revision_applies_its_files_in_procrastinate_s_order() -> None:
    """Which is by name — a later file may build on an earlier one."""
    named = _named_by_revisions()

    assert named, "no revision applies procrastinate's schema"
    for revision, names in named.items():
        assert names == sorted(names), revision


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


async def _abandon(job_queue: InMemoryConnector, *job_ids: int) -> None:
    """Leave the jobs as a worker killed minutes ago would: running, forever."""
    job_queue.workers[99] = datetime.now(UTC) - timedelta(minutes=5)
    for job_id in job_ids:
        job_queue.jobs[job_id].update(status="doing", worker_id=99)


def _refuse_retry(
    monkeypatch: pytest.MonkeyPatch, job_queue: InMemoryConnector, job_id: int, error: Exception
) -> None:
    """Make queueing `job_id` again fail as Postgres would; other jobs retry as usual."""
    retry = job_queue.retry_job_run

    async def refuse(**arguments: Any) -> None:
        if arguments["job_id"] == job_id:
            raise error
        await retry(**arguments)

    monkeypatch.setattr(job_queue, "retry_job_run", refuse)


async def test_a_dead_job_whose_replacement_is_waiting_is_given_up(
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A queueing lock allows one waiting job. The dead one was running, so a
    second could be queued behind it; queueing the dead one again would make
    two, and Postgres refuses. It must neither stop the sweep nor stay behind
    for the next one to trip over."""
    dead = await ping.configure(queueing_lock="reset:alice").defer_async()
    after_it = await ping.defer_async()
    await _abandon(job_queue, dead, after_it)
    replacement = await ping.configure(queueing_lock="reset:alice").defer_async()
    # The in-memory queue does not enforce the lock on a retry; Postgres does.
    _refuse_retry(
        monkeypatch,
        job_queue,
        dead,
        UniqueViolation(constraint_name=QUEUEING_LOCK_CONSTRAINT, queueing_lock="reset:alice"),
    )

    sweep = await retry_stalled_jobs.configure(task_kwargs={"timestamp": 0}).defer_async()
    await run_jobs()

    assert job_queue.jobs[dead]["status"] == "aborted"
    assert job_queue.jobs[after_it]["status"] == "succeeded"
    assert job_queue.jobs[replacement]["status"] == "succeeded"
    assert job_queue.jobs[sweep]["status"] == "succeeded"
    assert "given up, a newer job with its queueing lock is already waiting" in caplog.text


async def test_a_job_that_cannot_be_queued_again_does_not_hold_up_the_rest(
    run_jobs: RunJobs,
    job_queue: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stuck = await ping.defer_async()
    after_it = await ping.defer_async()
    await _abandon(job_queue, stuck, after_it)
    _refuse_retry(monkeypatch, job_queue, stuck, ConnectorException("connection lost"))

    sweep = await retry_stalled_jobs.configure(task_kwargs={"timestamp": 0}).defer_async()
    await run_jobs()

    assert job_queue.jobs[after_it]["status"] == "succeeded"
    assert job_queue.jobs[stuck]["status"] == "doing"
    # Failed, so the job nobody could rescue is more than a line in the log.
    assert job_queue.jobs[sweep]["status"] == "failed"
    assert f"Job {stuck} (ping) was left behind by a dead worker and could not be" in caplog.text


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
