"""The worker loop.

What matters here is not that it muxes -- that is covered elsewhere -- but that
it never leaves a job stuck, because a stuck job is a shim that waits until its
timeout and then fails a perfectly good import.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.application.interfaces.jobs import JobRecord
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest, fingerprint
from src.db.session import DBManager
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.worker.service import ImportWorker

REQUEST = ImportRequest(
    app="radarr",
    source_path=Path("/downloads/a.mkv"),
    destination_path=Path("/library/a.mkv"),
)
FINGERPRINT = fingerprint({"source_path": "/downloads/a.mkv"})


class RecordingRunner:
    """Stands in for RunImportJobUseCase."""

    def __init__(self, jobs: SqlAlchemyJobRepository, error: Exception | None = None) -> None:
        self._jobs = jobs
        self._error = error
        self.seen: list[str] = []

    async def execute(self, job: JobRecord) -> None:
        self.seen.append(job.id)
        if self._error is not None:
            raise self._error
        await self._jobs.succeed(job.id, ImportOutcome(move_status="DeferMove", reason="s"), None)


@pytest.fixture
def jobs(db: DBManager) -> SqlAlchemyJobRepository:
    return SqlAlchemyJobRepository(db)


@pytest.fixture
def worker_state(db: DBManager) -> SqlAlchemyWorkerStateRepository:
    return SqlAlchemyWorkerStateRepository(db)


def build(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    runner: RecordingRunner,
) -> ImportWorker:
    return ImportWorker(
        jobs=jobs,
        worker_state=worker_state,
        run_job=runner,  # type: ignore[arg-type]
    )


async def run_briefly(worker: ImportWorker, seconds: float = 0.4) -> None:
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(seconds)
    worker.stop()
    await asyncio.wait_for(task, timeout=5)


async def test_a_queued_job_is_picked_up(
    jobs: SqlAlchemyJobRepository, worker_state: SqlAlchemyWorkerStateRepository
) -> None:
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    runner = RecordingRunner(jobs)

    await run_briefly(build(jobs, worker_state, runner))

    assert runner.seen == ["job-1"]
    found = await jobs.get("job-1")
    assert found is not None
    assert found.state == "succeeded"


async def test_the_heartbeat_is_written(
    jobs: SqlAlchemyJobRepository, worker_state: SqlAlchemyWorkerStateRepository
) -> None:
    """A dead worker is otherwise indistinguishable from a slow mux."""
    assert await worker_state.last_seen() is None

    await run_briefly(build(jobs, worker_state, RecordingRunner(jobs)))

    assert await worker_state.last_seen() is not None


async def test_bookkeeping_failure_does_not_leave_a_job_running(
    jobs: SqlAlchemyJobRepository, worker_state: SqlAlchemyWorkerStateRepository
) -> None:
    """Otherwise the shim polls a job nothing is working on until it times out."""
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    runner = RecordingRunner(jobs, error=RuntimeError("bookkeeping exploded"))

    await run_briefly(build(jobs, worker_state, runner))

    found = await jobs.get("job-1")
    assert found is not None
    assert found.state == "failed"
    assert "bookkeeping exploded" in (found.error or "")


async def test_startup_fails_jobs_left_behind_by_a_dead_worker(
    jobs: SqlAlchemyJobRepository, worker_state: SqlAlchemyWorkerStateRepository
) -> None:
    """The mux may have half-written the destination, so the import must fail."""
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    await jobs.claim_next()

    await build(jobs, worker_state, RecordingRunner(jobs)).reconcile()

    found = await jobs.get("job-1")
    assert found is not None
    assert found.state == "failed"
    assert "restarted" in (found.error or "")
