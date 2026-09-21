"""Run one claimed import. Runs in the worker process.

The mux itself is synchronous and can take hours, so it executes on a worker
thread; only the bookkeeping around it is async.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import JobRecord, JobRepository
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.core.logging import get_logger
from src.domain.enums import LogComponent

log = get_logger(LogComponent.USECASE_JOBS)


class RunImportJobUseCase:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        history: HistoryRepository,
        handler: HandleImportUseCase,
    ) -> None:
        self._jobs = jobs
        self._history = history
        self._handler = handler

    async def execute(self, job: JobRecord) -> None:
        request = job.request
        bound = log.bind(
            job_id=job.id,
            app=request.app,
            mode=request.transfer_mode,
            source=request.source_path,
        )
        bound.info("import started")
        try:
            outcome = await asyncio.to_thread(self._handler.execute, request)
        except Exception as exc:
            # handle_import degrades to DeferMove internally, so reaching here
            # means the daemon itself broke; the shim turns it into a failed
            # import rather than letting *arr move a possibly half-muxed file.
            bound.exception("import job failed")
            await self._jobs.fail(job.id, f"{type(exc).__name__}: {exc}")
            return
        bound.info("import settled", status=outcome.move_status, reason=outcome.reason)
        await self._jobs.succeed(job.id, outcome, await self._record(request, outcome))

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
            log.exception("could not record history", source=request.source_path)
            return None
