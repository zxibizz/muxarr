"""The import worker.

Runs as its own process beside the API. The API only ever queues work; this is
the only thing that muxes, so the mkvmerge dependency and the write access to
the library live here alone.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress

from src.application.interfaces.jobs import JobRecord, JobRepository, WorkerStateRepository
from src.application.use_cases.imports.run_job import RunImportJobUseCase
from src.core.logging import get_logger
from src.domain.enums import LogComponent

log = get_logger(LogComponent.WORKER)

# How long to wait before looking for work again. A mux runs for minutes at
# least, so a second of pickup latency is not worth a busier poll.
IDLE_POLL_INTERVAL = 0.5

# Writing the heartbeat on every pass would be a needless write per poll.
HEARTBEAT_INTERVAL = 5.0

# Generous next to HEARTBEAT_INTERVAL: a worker busy with a mux still beats
# between polls, and a brief stall is not worth reporting as dead.
WORKER_STALE_AFTER = HEARTBEAT_INTERVAL * 6


class ImportWorker:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        worker_state: WorkerStateRepository,
        run_job: RunImportJobUseCase,
        max_concurrent_muxes: int = 1,
        job_ttl_seconds: float = 3600.0,
    ) -> None:
        self._jobs = jobs
        self._worker_state = worker_state
        self._run_job = run_job
        self._max_concurrent = max(1, max_concurrent_muxes)
        self._job_ttl = job_ttl_seconds
        self._stop = asyncio.Event()
        self._last_heartbeat = 0.0

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        await self.reconcile()
        running: set[asyncio.Task[None]] = set()

        while not self._stop.is_set():
            await self._beat()
            await self._fill(running)

            if running:
                await asyncio.wait(
                    running, timeout=IDLE_POLL_INTERVAL, return_when=asyncio.FIRST_COMPLETED
                )
            else:
                await self._idle()
                await self._jobs.prune(self._job_ttl)

        if running:
            log.info("waiting for in-flight muxes", count=len(running))
            await asyncio.gather(*running, return_exceptions=True)

    async def reconcile(self) -> None:
        """Fail anything a previous worker left unfinished.

        This process is the only consumer of the queue, so a job still marked
        running at startup died with the worker that claimed it. Failing it
        makes the shim fail the import, which is the safe answer when a mux may
        have half-written the destination.
        """
        try:
            stale = await self._jobs.fail_running("worker restarted before the job finished")
        except Exception:
            log.exception("could not reconcile interrupted jobs")
            return
        if stale:
            log.warning("failed jobs interrupted by a restart", count=stale)

    async def _fill(self, running: set[asyncio.Task[None]]) -> None:
        while not self._stop.is_set() and len(running) < self._max_concurrent:
            job = await self._claim()
            if job is None:
                return
            task = asyncio.create_task(self._execute(job))
            running.add(task)
            task.add_done_callback(running.discard)

    async def _claim(self) -> JobRecord | None:
        try:
            return await self._jobs.claim_next()
        except Exception:
            log.exception("could not claim a job")
            return None

    async def _execute(self, job: JobRecord) -> None:
        try:
            await self._run_job.execute(job)
        except Exception as exc:
            # run_job handles its own failures; reaching here means the
            # bookkeeping itself broke, and the job must not stay running.
            log.exception("job bookkeeping failed", job_id=job.id)
            await self._jobs.fail(job.id, f"{type(exc).__name__}: {exc}")

    async def _beat(self) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < HEARTBEAT_INTERVAL:
            return
        try:
            await self._worker_state.heartbeat()
        except Exception:
            log.exception("could not write the worker heartbeat")
            return
        self._last_heartbeat = now

    async def _idle(self) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=IDLE_POLL_INTERVAL)
