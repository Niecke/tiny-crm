"""The background worker: runs what the API deferred (app/jobs/, #206).

    python -m app.worker

The same image as the API, started with a different command — same models,
same mail templates, never a version apart. Reads the same environment, of
which it needs DATABASE_URL, JWT_SECRET (it signs the reset links it mails) and
the mail settings.

One process, several pools (WORKER_POOLS). Each pool is a procrastinate worker
with its own queues and its own slots, so mail is never stuck behind a long
job on another queue. They share the event loop, the process and its memory
limit — which is why CPU-bound tasks must be sync (see app/jobs/), and why an
out-of-memory kill in one pool takes the others down with it until the pod is
back. If that ever happens in practice, run one Deployment per pool: the same
command with a one-pool WORKER_POOLS.

Stopping: on SIGTERM or SIGINT every pool stops taking jobs and lets the
running ones finish, for up to WORKER_SHUTDOWN_GRACE_SECONDS. What is still
running then is aborted; a job whose worker died without even that is handed
out again by `retry_stalled_jobs`. Either way a task may run twice.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import DEFAULT_JWT_SECRET, Environment, WorkerPool, settings
from app.jobs import jobs_app
from app.logging_config import configure_logging

# Not __name__: started with `python -m`, that would be "__main__" in every log line.
logger = logging.getLogger("app.worker")

# Touched while the event loop turns; the chart's liveness probe checks its age.
# Nothing listens on a port here, so there is nothing for an HTTP probe to ask.
ALIVE_FILE = Path("/tmp/worker-alive")
ALIVE_INTERVAL_SECONDS = 15


async def _keep_alive_file(path: Path, interval: float) -> None:
    """Proof of a turning event loop, and of nothing more.

    Deliberately not a database check: an unreachable database would then
    restart every worker and slow the recovery down, as it would for the API
    (see the probes in charts/tinycrm/templates/backend.yaml). A loop blocked
    by a task that should have been sync, on the other hand, stops this too.
    """
    while True:
        path.touch()
        await asyncio.sleep(interval)


async def run(
    pools: Sequence[WorkerPool],
    *,
    stop: asyncio.Event,
    alive_file: Path = ALIVE_FILE,
    alive_interval: float = ALIVE_INTERVAL_SECONDS,
) -> int:
    """Run every pool until `stop` is set; the process's exit code.

    Non-zero when a pool ended by itself. procrastinate stops a worker whose
    LISTEN connection or heartbeat failed, and a process with one pool silently
    gone would look alive while its queue fills up. Exiting has the pod
    restarted with all of them.
    """
    async with jobs_app.open_async():
        workers = [
            asyncio.create_task(
                jobs_app.run_worker_async(
                    name=pool.name,
                    queues=pool.queues,
                    concurrency=pool.concurrency,
                    shutdown_graceful_timeout=settings.worker_shutdown_grace_seconds,
                    # One process-wide handler in main() instead: each pool
                    # installing its own would replace the previous pool's.
                    install_signal_handlers=False,
                ),
                name=f"pool {pool.name}",
            )
            for pool in pools
        ]
        alive = asyncio.create_task(_keep_alive_file(alive_file, alive_interval))
        stopping = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait([stopping, *workers], return_when=asyncio.FIRST_COMPLETED)
            ended = [worker for worker in workers if worker.done()]
            for worker in ended:
                logger.error(
                    "Worker %s ended without being asked to; stopping the others",
                    worker.get_name(),
                    exc_info=worker.exception(),
                )
            # Cancelling is procrastinate's graceful stop: no new jobs, and the
            # running ones get their grace period before run_worker_async returns.
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            alive.cancel()
            stopping.cancel()
    return 1 if ended else 0


async def _main() -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    return await run(settings.worker_pools, stop=stop)


def main() -> int:
    configure_logging()
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        # The one insecure default that matters here: the worker signs reset
        # links with it. The API's full check (app/main.py) covers settings
        # this process never reads.
        if settings.environment is Environment.production:
            logger.error("Refusing to start: JWT_SECRET is the built-in placeholder")
            return 2
        logger.warning("JWT_SECRET is the built-in placeholder (allowed outside production)")
    if not settings.worker_pools:
        logger.error("Refusing to start: WORKER_POOLS is empty, there is nothing to run")
        return 2
    logger.info(
        "Starting worker pools: %s",
        "; ".join(
            f"{pool.name} ({', '.join(pool.queues)}) ×{pool.concurrency}"
            for pool in settings.worker_pools
        ),
    )
    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
