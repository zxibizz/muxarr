"""Run one claimed import. Runs in the worker process.

The mux itself is synchronous and can take hours, so it executes on a worker
thread; only the bookkeeping around it is async.

Everything the import logs is captured and stored, both on the job while it runs
and on the history row it produces. That is the only account of a failed job:
one that never reaches the history writes no operation row at all.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import JobRecord, JobRepository
from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.core.logging import capture_log, get_logger
from src.domain.enums import LogComponent
from src.domain.journal import LogEntry

log = get_logger(LogComponent.USECASE_JOBS)

# How often the growing log is pushed to the job row. Flushes are change-driven,
# so a long silent remux writes nothing.
FLUSH_INTERVAL = 2.0


class RunImportJobUseCase:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        history: HistoryRepository,
        handler: HandleImportUseCase,
        log_max_entries: int = 500,
    ) -> None:
        self._jobs = jobs
        self._history = history
        self._handler = handler
        self._log_max_entries = log_max_entries

    async def execute(self, job: JobRecord) -> None:
        request = job.request
        bound = log.bind(
            job_id=job.id,
            app=request.app,
            mode=request.transfer_mode,
            source=request.source_path,
        )
        with capture_log(self._log_max_entries) as entries:
            bound.info("import started")
            follower = asyncio.create_task(self._follow(job.id, entries))
            try:
                outcome = await asyncio.to_thread(self._handler.execute, request)
            except Exception as exc:
                # handle_import degrades to DeferMove internally, so reaching here
                # means the daemon itself broke; the shim turns it into a failed
                # import rather than letting *arr move a possibly half-muxed file.
                bound.exception("import job failed")
                await self._stop(follower)
                await self._flush(job.id, entries)
                await self._jobs.fail(job.id, f"{type(exc).__name__}: {exc}")
                return
            bound.info("import settled", status=outcome.move_status, reason=outcome.reason)
            await self._stop(follower)
            await self._flush(job.id, entries)
            history_id = await self._record(request, outcome, entries)
        await self._jobs.succeed(job.id, outcome, history_id)

    async def _follow(self, job_id: str, entries: list[LogEntry]) -> None:
        """Publish the log as it grows, so a running import can be watched."""
        written = 0
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            if len(entries) == written:
                continue
            written = len(entries)
            await self._flush(job_id, entries)

    @staticmethod
    async def _stop(follower: asyncio.Task[None]) -> None:
        follower.cancel()
        with suppress(asyncio.CancelledError):
            await follower

    async def _flush(self, job_id: str, entries: list[LogEntry]) -> None:
        try:
            await self._jobs.save_log(job_id, list(entries))
        except Exception:
            # The log is an explanation, never a reason to fail an import.
            log.exception("could not store the job log", job_id=job_id)

    async def _record(
        self, request: ImportRequest, outcome: ImportOutcome, entries: list[LogEntry]
    ) -> int | None:
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
                log=list(entries),
                duration_ms=outcome.duration_ms,
                source_bytes=outcome.source_bytes,
                output_bytes=outcome.output_bytes,
                dry_run=request.dry_run,
            )
        except Exception:
            # Losing a history row must never turn a good import into a failure.
            log.exception("could not record history", source=request.source_path)
            return None
