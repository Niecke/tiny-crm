"""The worker process, `python -m app.worker`: its pools, its stop, its exit code.

Against the in-memory queue. The real path — Postgres, LISTEN, the image's own
command — is ci/smoke.sh's, which pings a running worker.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from procrastinate.testing import InMemoryConnector
from pydantic import ValidationError

from app import worker
from app.config import DEFAULT_JWT_SECRET, Environment, Settings, WorkerPool, settings
from app.jobs import DEFAULT_QUEUE, MAIL_QUEUE, jobs_app, ping

MAIL_POOL = WorkerPool(name="mail", queues=[MAIL_QUEUE], concurrency=2)
DEFAULT_POOL = WorkerPool(name="default", queues=[DEFAULT_QUEUE])


async def _until(condition: Any, seconds: float = 5) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.01)


async def test_every_pool_runs_its_queue_until_told_to_stop(
    job_queue: InMemoryConnector, tmp_path: Path
) -> None:
    alive = tmp_path / "worker-alive"
    await ping.configure(queue=MAIL_QUEUE).defer_async()
    await ping.configure(queue=DEFAULT_QUEUE).defer_async()
    stop = asyncio.Event()

    running = asyncio.create_task(
        worker.run([MAIL_POOL, DEFAULT_POOL], stop=stop, alive_file=alive, alive_interval=0.01)
    )
    await _until(lambda: all(job["status"] == "succeeded" for job in job_queue.jobs.values()))
    assert alive.exists()
    assert not running.done()

    stop.set()

    assert await asyncio.wait_for(running, 5) == 0
    # Both pools signed off: nothing is left registered as a worker.
    assert job_queue.workers == {}


async def test_a_pool_leaves_other_pools_queues_alone(
    job_queue: InMemoryConnector, tmp_path: Path
) -> None:
    """Mail's slots are mail's: no other pool may take a job from its queue."""
    await ping.configure(queue=MAIL_QUEUE).defer_async()
    await ping.configure(queue=DEFAULT_QUEUE).defer_async()
    stop = asyncio.Event()

    running = asyncio.create_task(
        worker.run([DEFAULT_POOL], stop=stop, alive_file=tmp_path / "alive")
    )
    await _until(lambda: job_queue.jobs[2]["status"] == "succeeded")
    stop.set()
    await asyncio.wait_for(running, 5)

    assert job_queue.jobs[1]["status"] == "todo"


async def test_a_pool_that_ends_by_itself_takes_the_process_down(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One pool silently gone would look like a healthy worker with a full queue."""
    stopped: list[str] = []

    async def run_worker(**options: Any) -> None:
        if options["name"] == "mail":
            raise RuntimeError("LISTEN connection lost")
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(options["name"])

    monkeypatch.setattr(jobs_app, "run_worker_async", run_worker)

    code = await asyncio.wait_for(
        worker.run([MAIL_POOL, DEFAULT_POOL], stop=asyncio.Event(), alive_file=tmp_path / "alive"),
        5,
    )

    assert code == 1
    assert stopped == ["default"]
    assert "pool mail ended without being asked to" in caplog.text


# Start-up checks.


@pytest.fixture
def quiet_start(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """main() without its side effects: no logging reconfigured, no pool started."""
    started: list[bool] = []

    async def fake_main() -> int:
        started.append(True)
        return 0

    monkeypatch.setattr(worker, "configure_logging", lambda: None)
    monkeypatch.setattr(worker, "_main", fake_main)
    return started


def test_production_refuses_the_placeholder_secret(
    monkeypatch: pytest.MonkeyPatch, quiet_start: list[bool]
) -> None:
    """The worker signs the reset links it mails."""
    monkeypatch.setattr(settings, "jwt_secret", DEFAULT_JWT_SECRET)
    monkeypatch.setattr(settings, "environment", Environment.production)

    assert worker.main() == 2
    assert quiet_start == []


def test_development_starts_on_the_placeholder_secret(
    monkeypatch: pytest.MonkeyPatch, quiet_start: list[bool]
) -> None:
    monkeypatch.setattr(settings, "jwt_secret", DEFAULT_JWT_SECRET)

    assert worker.main() == 0
    assert quiet_start == [True]


def test_no_pools_is_a_refusal_not_an_idle_worker(
    monkeypatch: pytest.MonkeyPatch, quiet_start: list[bool]
) -> None:
    monkeypatch.setattr(settings, "worker_pools", [])

    assert worker.main() == 2
    assert quiet_start == []


# WORKER_POOLS.


def test_the_default_pools_keep_mail_apart() -> None:
    pools = {pool.name: pool for pool in Settings(_env_file=None).worker_pools}

    assert pools["mail"].queues == [MAIL_QUEUE]
    assert all(MAIL_QUEUE not in pool.queues for name, pool in pools.items() if name != "mail")
    # Housekeeping runs on the default queue; a worker has to serve it.
    assert any(DEFAULT_QUEUE in pool.queues for pool in pools.values())


def test_pools_are_read_from_the_environment_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """How the chart hands them over, and how a pool gets a Deployment of its own."""
    monkeypatch.setenv("WORKER_POOLS", '[{"name": "mail", "queues": ["mail"], "concurrency": 4}]')

    assert Settings(_env_file=None).worker_pools == [
        WorkerPool(name="mail", queues=["mail"], concurrency=4)
    ]


@pytest.mark.parametrize(
    "pools",
    [
        '[{"name": "mail", "queues": [], "concurrency": 1}]',
        '[{"name": "mail", "queues": ["mail"], "concurrency": 0}]',
    ],
)
def test_a_pool_that_could_never_run_a_job_is_rejected(
    monkeypatch: pytest.MonkeyPatch, pools: str
) -> None:
    monkeypatch.setenv("WORKER_POOLS", pools)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
