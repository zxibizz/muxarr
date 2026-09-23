"""The worker loop.

What matters here is not that it muxes -- that is covered elsewhere -- but that
it never leaves a job stuck, because a stuck job is a shim that waits until its
timeout and then fails a perfectly good import.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from src.application.interfaces.history import NewOperation
from src.application.interfaces.jobs import JobRecord
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest, fingerprint
from src.db.session import DBManager
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.settings.config import Settings
from src.worker.service import IDLE_POLL_INTERVAL, ImportWorker

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
    history: SqlAlchemyHistoryRepository,
    runner: RecordingRunner,
    history_max_records: int = 200,
    settings: Callable[[], Settings] | None = None,
    sync: Callable[[], Awaitable[bool]] | None = None,
) -> ImportWorker:
    fixed = Settings(read_roots=(Path("/downloads"),), history_max_records=history_max_records)
    return ImportWorker(
        jobs=jobs,
        worker_state=worker_state,
        history=history,
        run_job=lambda: runner,  # type: ignore[arg-type,return-value]
        settings=settings or (lambda: fixed),
        sync=sync,
    )


async def run_briefly(worker: ImportWorker, seconds: float = 0.4) -> None:
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(seconds)
    worker.stop()
    await asyncio.wait_for(task, timeout=5)


async def test_a_queued_job_is_picked_up(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    runner = RecordingRunner(jobs)

    await run_briefly(build(jobs, worker_state, history, runner))

    assert runner.seen == ["job-1"]
    found = await jobs.get("job-1")
    assert found is not None
    assert found.state == "succeeded"


async def test_the_heartbeat_is_written(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    """A dead worker is otherwise indistinguishable from a slow mux."""
    assert await worker_state.last_seen() is None

    await run_briefly(build(jobs, worker_state, history, RecordingRunner(jobs)))

    assert await worker_state.last_seen() is not None


async def test_bookkeeping_failure_does_not_leave_a_job_running(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    """Otherwise the shim polls a job nothing is working on until it times out."""
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    runner = RecordingRunner(jobs, error=RuntimeError("bookkeeping exploded"))

    await run_briefly(build(jobs, worker_state, history, runner))

    found = await jobs.get("job-1")
    assert found is not None
    assert found.state == "failed"
    assert "bookkeeping exploded" in (found.error or "")


async def test_startup_fails_jobs_left_behind_by_a_dead_worker(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    """The mux may have half-written the destination, so the import must fail."""
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    await jobs.claim_next()

    await build(jobs, worker_state, history, RecordingRunner(jobs)).reconcile()

    found = await jobs.get("job-1")
    assert found is not None
    assert found.state == "failed"
    assert "restarted" in (found.error or "")


async def test_history_is_trimmed_to_the_cap_while_idle(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    """Nothing else ever deletes an operation, so the table would grow forever."""
    for index in range(5):
        await history.record(
            NewOperation(
                app="radarr",
                title=f"{index}.mkv",
                move_status="DeferMove",
                reason="no external tracks",
                source_path=f"/downloads/{index}.mkv",
                destination_path=f"/library/{index}.mkv",
            )
        )

    await run_briefly(
        build(jobs, worker_state, history, RecordingRunner(jobs), history_max_records=2)
    )

    page = await history.list()
    assert [op.title for op in page.items] == ["4.mkv", "3.mkv"]


async def test_settings_are_re_read_while_running(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    """A change saved in the browser must not need a container restart."""
    syncs = 0

    async def sync() -> bool:
        nonlocal syncs
        syncs += 1
        return False

    await run_briefly(build(jobs, worker_state, history, RecordingRunner(jobs), sync=sync))

    assert syncs == 1


async def test_a_reload_failure_does_not_stop_the_queue(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    """Imports matter more than settings freshness."""
    await jobs.create_or_get("job-1", FINGERPRINT, REQUEST)
    runner = RecordingRunner(jobs)

    async def sync() -> bool:
        raise RuntimeError("database is away")

    await run_briefly(build(jobs, worker_state, history, runner, sync=sync))

    assert runner.seen == ["job-1"]


async def test_a_raised_concurrency_takes_effect_without_a_restart(
    jobs: SqlAlchemyJobRepository,
    worker_state: SqlAlchemyWorkerStateRepository,
    history: SqlAlchemyHistoryRepository,
) -> None:
    current = Settings(read_roots=(Path("/downloads"),), max_concurrent_muxes=1)
    started = asyncio.Event()
    release = asyncio.Event()
    concurrent = 0
    peak = 0

    class Blocking(RecordingRunner):
        async def execute(self, job: JobRecord) -> None:
            nonlocal concurrent, peak
            self.seen.append(job.id)
            concurrent += 1
            peak = max(peak, concurrent)
            started.set()
            await release.wait()
            concurrent -= 1

    for index in range(2):
        await jobs.create_or_get(f"job-{index}", f"{FINGERPRINT}{index}", REQUEST)

    runner = Blocking(jobs)
    worker = build(jobs, worker_state, history, runner, settings=lambda: current)
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(started.wait(), timeout=5)

    current = Settings(read_roots=(Path("/downloads"),), max_concurrent_muxes=2)
    # Long enough for the loop to come back round off its idle wait.
    await asyncio.sleep(IDLE_POLL_INTERVAL * 2)
    assert peak == 2

    release.set()
    worker.stop()
    await asyncio.wait_for(task, timeout=5)
