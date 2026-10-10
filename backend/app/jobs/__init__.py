"""The job queue: work that leaves the request and runs in the worker (#206).

Mail is the first of it — a password-reset request used to wait for Brevo
inside the HTTP request — and anything slow follows: thumbnails, imports.

The queue is procrastinate on the application's own Postgres. No extra service
to run or back up, and retries, queueing locks and worker heartbeats come with
it. The price is a second database driver: procrastinate speaks psycopg, the
app asyncpg, each with its own small pool.

    API      opens `jobs_app` in its lifespan and only ever defers.
    worker   `python -m app.worker`, the same image, runs what was deferred.

Three rules for every task in this package:

* **No secrets in the arguments.** They are rows in `procrastinate_jobs` and so
  in the nightly backup. Pass an id; load, mint and render in the task.
* **Idempotent.** Delivery is at-least-once — a worker killed between doing the
  work and recording it leaves the job to be run again.
* **CPU-bound work is a plain `def`.** procrastinate runs sync tasks in a
  thread. An `async def` that computes blocks the loop every pool shares, the
  mail pool included.

Enqueueing is not transactional with the SQLAlchemy session: a job is deferred
on procrastinate's connection and is visible to the worker at once, whatever
the request's own transaction does afterwards. Fine while no job depends on a
row written in the same request; one that does needs an outbox first.
"""

from __future__ import annotations

import logging

from procrastinate import App, JobContext, PsycopgConnector
from procrastinate.exceptions import ProcrastinateException, UniqueViolation
from procrastinate.jobs import Job, Status
from procrastinate.manager import QUEUEING_LOCK_CONSTRAINT, JobManager
from sqlalchemy.engine import make_url

from app.config import settings

logger = logging.getLogger(__name__)

# Queue names. Which worker pool serves which queue is WORKER_POOLS
# (app/config.py); a queue no pool lists is never worked.
MAIL_QUEUE = "mail"
DEFAULT_QUEUE = "default"

# A worker that has not reported in for this long is taken for dead, and what
# it was running is handed out again. Three missed beats of the default 10 s.
STALLED_WORKER_SECONDS = 30

# How long finished jobs stay for the status page and for diagnosis.
KEEP_SUCCEEDED_HOURS = 24 * 7
KEEP_FAILED_HOURS = 24 * 30


def database_dsn(database_url: str) -> str:
    """DATABASE_URL as libpq reads it: the same server, without SQLAlchemy's
    `+asyncpg` driver suffix."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


jobs_app = App(
    connector=PsycopgConnector(
        conninfo=database_dsn(settings.database_url),
        # Deferring and bookkeeping are single short statements. Each worker
        # pool holds one more connection outside this pool, for LISTEN.
        min_size=1,
        max_size=2,
    ),
    # Every module that defines tasks. A worker that meets a job whose module
    # it never imported fails it as "task not found".
    import_paths=["app.jobs.mail"],
    worker_defaults={"stalled_worker_timeout": STALLED_WORKER_SECONDS},
)


@jobs_app.task(name="ping", queue=DEFAULT_QUEUE)
async def ping() -> None:
    """Does nothing, successfully. `python -m app.cli ping-worker` defers one
    per queue to prove a worker is taking jobs from it."""


# --- Housekeeping ------------------------------------------------------------
#
# The queue's own upkeep, the one thing scheduled from inside the worker: it is
# only needed while a worker runs, and procrastinate defers each slot once
# however many replicas there are. On the default queue, so every deployment
# has to serve that one.


@jobs_app.periodic(cron="*/5 * * * *")
@jobs_app.task(
    name="retry_stalled_jobs",
    queue=DEFAULT_QUEUE,
    queueing_lock="retry_stalled_jobs",
    pass_context=True,
)
async def retry_stalled_jobs(context: JobContext, timestamp: int) -> None:
    """Hand out again what a dead worker was running.

    A worker that is killed — OOM, node gone — leaves its jobs in `doing`
    forever; nothing else would ever pick them up.

    Job by job: one that cannot be queued again must not keep the ones after
    it waiting for a sweep that gets past it. The sweep still ends as failed
    then, so the job that is stuck shows up as more than a log line.
    """
    manager = context.app.job_manager
    stuck = 0
    for job in await manager.get_stalled_jobs(seconds_since_heartbeat=STALLED_WORKER_SECONDS):
        try:
            await _hand_out_again(manager, job)
        except ProcrastinateException as exc:
            stuck += 1
            logger.error(
                "Job %s (%s) was left behind by a dead worker and could not be queued again: %s",
                job.id,
                job.task_name,
                type(exc).__name__,
            )
    if stuck:
        raise RuntimeError(f"{stuck} job(s) of a dead worker could not be queued again")


async def _hand_out_again(manager: JobManager, job: Job) -> None:
    try:
        await manager.retry_job(job)
    except UniqueViolation as exc:
        if exc.constraint_name != QUEUEING_LOCK_CONSTRAINT:
            raise
        # A queueing lock allows one *waiting* job. This one was running, so a
        # second could be queued behind it — and now is: its replacement is
        # already waiting, and queueing this one again would make two. Ended
        # as aborted rather than left in `doing`, where every sweep would trip
        # over it again.
        await manager.finish_job(job, status=Status.ABORTED, delete_job=False)
        logger.warning(
            "Job %s (%s) was left behind by a dead worker; given up, a newer job "
            "with its queueing lock is already waiting",
            job.id,
            job.task_name,
        )
        return
    logger.warning(
        "Job %s (%s) was left behind by a dead worker; queued again", job.id, job.task_name
    )


@jobs_app.periodic(cron="17 3 * * *")
@jobs_app.task(
    name="remove_old_jobs",
    queue=DEFAULT_QUEUE,
    queueing_lock="remove_old_jobs",
    pass_context=True,
)
async def remove_old_jobs(context: JobContext, timestamp: int) -> None:
    """Delete finished jobs: succeeded ones after a week, the rest after a month."""
    manager = context.app.job_manager
    await manager.delete_old_jobs(nb_hours=KEEP_SUCCEEDED_HOURS)
    await manager.delete_old_jobs(
        nb_hours=KEEP_FAILED_HOURS,
        include_failed=True,
        include_cancelled=True,
        include_aborted=True,
    )
