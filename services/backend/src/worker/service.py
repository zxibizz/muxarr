"""The import worker.

Runs as its own process beside the API. The API only ever queues work; this is
the only thing that muxes, so the mkvmerge dependency and the write access to
the library live here alone.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import JobRecord, JobRepository, WorkerStateRepository
from src.application.use_cases.imports.run_job import RunImportJobUseCase
from src.core.logging import get_logger
from src.domain.enums import LogComponent
from src.settings.config import Settings

log = get_logger(LogComponent.WORKER)

# How long to wait before looking for work again. A mux runs for minutes at
# least, so a second of pickup latency is not worth a busier poll.
IDLE_POLL_INTERVAL = 0.5

# Writing the heartbeat on every pass would be a needless write per poll.
HEARTBEAT_INTERVAL = 5.0

# Generous next to HEARTBEAT_INTERVAL: a worker busy with a mux still beats
# between polls, and a brief stall is not worth reporting as dead.
WORKER_STALE_AFTER = HEARTBEAT_INTERVAL * 6

# Retention is measured in hours and hundreds of rows, so sweeping on every
# idle pass would be two pointless DELETEs a second.
SWEEP_INTERVAL = 60.0

# A setting saved in the browser should take effect before the user has
# finished reading the confirmation.
SETTINGS_POLL_INTERVAL = 5.0


class ImportWorker:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        worker_state: WorkerStateRepository,
        history: HistoryRepository,
        # Callables, not values: settings change under a running worker, and
        # the use case is rebuilt when they do.
        run_job: Callable[[], RunImportJobUseCase],
        settings: Callable[[], Settings],
        sync: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._jobs = jobs
        self._worker_state = worker_state
        self._history = history
        self._run_job = run_job
        self._settings = settings
        self._sync = sync
        self._stop = asyncio.Event()
        self._last_heartbeat = 0.0
        self._last_sweep = 0.0
        self._last_reload = 0.0

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        await self.reconcile()
        running: set[asyncio.Task[None]] = set()

        while not self._stop.is_set():
            await self._reload()
            await self._beat()
            await self._fill(running)

            if running:
                await asyncio.wait(
                    running, timeout=IDLE_POLL_INTERVAL, return_when=asyncio.FIRST_COMPLETED
                )
            else:
                await self._idle()
                await self._sweep()

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
        limit = max(1, self._settings().max_concurrent_muxes)
        while not self._stop.is_set() and len(running) < limit:
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
            await self._run_job().execute(job)
        except Exception as exc:
            # run_job handles its own failures; reaching here means the
            # bookkeeping itself broke, and the job must not stay running.
            log.exception("job bookkeeping failed", job_id=job.id)
            await self._jobs.fail(job.id, f"{type(exc).__name__}: {exc}")

    async def _reload(self) -> None:
        if self._sync is None:
            return
        now = time.monotonic()
        if now - self._last_reload < SETTINGS_POLL_INTERVAL:
            return
        self._last_reload = now
        try:
            await self._sync()
        except Exception:
            log.exception("could not reload settings")

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

    async def _sweep(self) -> None:
        """Evict finished jobs past their TTL and history past its cap.

        Only ever runs between muxes: retention is housekeeping, and a delete
        contending with a running import for the SQLite writer helps nobody.
        """
        now = time.monotonic()
        if now - self._last_sweep < SWEEP_INTERVAL:
            return
        self._last_sweep = now
        settings = self._settings()

        try:
            await self._jobs.prune(settings.job_ttl_seconds)
        except Exception:
            log.exception("could not prune finished jobs")

        try:
            removed = await self._history.prune(settings.history_max_records)
        except Exception:
            log.exception("could not trim the history")
            return
        if removed:
            log.info("trimmed history", removed=removed, kept=settings.history_max_records)
