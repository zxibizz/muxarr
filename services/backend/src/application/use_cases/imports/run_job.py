"""Queue an import and run it off the event loop.

The mux itself is synchronous and can run for hours, so it executes on a worker
thread; only the bookkeeping around it is async.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import Job, JobStore
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.application.use_cases.imports.handle_import import HandleImportUseCase

log = logging.getLogger(__name__)


class ImportJobService:
    def __init__(
        self,
        *,
        jobs: JobStore,
        history: HistoryRepository,
        handler: HandleImportUseCase,
        max_concurrent_muxes: int = 1,
    ) -> None:
        self._jobs = jobs
        self._history = history
        self._handler = handler
        # One mux at a time by default; concurrent remuxes on one spindle are
        # slower than running them back to back.
        self._semaphore = asyncio.Semaphore(max_concurrent_muxes)

    def submit(self, job_id: str, fingerprint: str, request: ImportRequest) -> Job:
        """Register the job and start it if this call created it."""
        job, created = self._jobs.create_or_get(job_id, fingerprint)
        if created:
            job.task = asyncio.create_task(self._run(job, request))
        return job

    async def wait(self, job_id: str, timeout: float) -> Job | None:
        return await self._jobs.wait(job_id, timeout)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def _run(self, job: Job, request: ImportRequest) -> None:
        log.info(
            "import job=%s app=%s mode=%s source=%s",
            job.id,
            request.app,
            request.transfer_mode,
            request.source_path,
        )
        try:
            self._jobs.start(job.id)
            async with self._semaphore:
                outcome = await asyncio.to_thread(self._handler.execute, request)
        except Exception as exc:
            # handle_import degrades to DeferMove internally, so reaching here
            # means the daemon itself broke; the shim turns it into a failed
            # import rather than letting *arr move a possibly half-muxed file.
            log.exception("import job %s failed", job.id)
            self._jobs.fail(job.id, f"{type(exc).__name__}: {exc}")
            return
        log.info("import result status=%s reason=%s", outcome.move_status, outcome.reason)
        self._jobs.succeed(job.id, outcome, await self._record(request, outcome))

    async def _record(self, request: ImportRequest, outcome: ImportOutcome) -> int | None:
        episode = request.episode_ref
        try:
            return await self._history.record(
                app=request.app,
                title=Path(request.source_path).name,
                move_status=outcome.move_status,
                reason=outcome.reason,
                source_path=str(request.source_path),
                destination_path=str(request.destination_path),
                media_file=str(outcome.media_file) if outcome.media_file else None,
                transfer_mode=request.transfer_mode,
                season=episode.season if episode else None,
                episodes=episode.episodes if episode else (),
                added_tracks=outcome.added_tracks,
                rejected_tracks=outcome.rejected_tracks,
                duration_ms=outcome.duration_ms,
                source_bytes=outcome.source_bytes,
                output_bytes=outcome.output_bytes,
                dry_run=request.dry_run,
            )
        except Exception:
            # Losing a history row must never turn a good import into a failure.
            log.exception("could not record history for %s", request.source_path)
            return None
