"""Settle the jobs a dead worker left behind.

A worker killed mid-mux leaves its job ``running`` and its staging file on disk:
multi-gigabyte, hidden, and never looked at again. The job is failed rather than
resumed, since the destination may be half-written; the staging file goes too.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.application.interfaces.jobs import MAX_JOB_PAGE_SIZE, JobRepository
from src.application.interfaces.placement import Placement, PlacementPolicy
from src.application.use_cases.imports.dto import OUTPUT_SUFFIX, ImportRequest
from src.core.logging import get_logger
from src.domain.enums import LogComponent
from src.domain.errors import MuxarrError
from src.domain.paths import PathGuard

log = get_logger(LogComponent.USECASE_JOBS)

INTERRUPTED = "worker restarted before the job finished"


class ReconcileInterruptedJobsUseCase:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        guard: PathGuard,
        placement: Placement,
        scratch_dir: Path | None,
    ) -> None:
        self._jobs = jobs
        self._guard = guard
        self._placement = placement
        self._policy = PlacementPolicy(scratch_dir=scratch_dir)

    async def execute(self) -> int:
        """Fail every job left ``running``, returning how many."""
        interrupted = await self._jobs.list(state="running", limit=MAX_JOB_PAGE_SIZE)
        failed = await self._jobs.fail_running(INTERRUPTED)
        for job in interrupted.items:
            for path in await asyncio.to_thread(self._discard, job.request):
                log.info("removed an interrupted mux's staging file", job_id=job.id, path=path)
        return failed

    def _discard(self, request: ImportRequest) -> list[Path]:
        try:
            destination = self._guard.check_destination(request.destination_path)
            output = self._guard.check_destination(destination.with_suffix(OUTPUT_SUFFIX))
        except MuxarrError:
            # The import was deferred at the guard, so it never staged anything.
            return []
        return self._placement.discard_staging(output, self._policy)
