"""Queue an import. Runs in the API process; does no work itself."""

from __future__ import annotations

from src.application.interfaces.jobs import JobRecord, JobRepository
from src.application.use_cases.imports.dto import ImportRequest
from src.core.logging import get_logger
from src.domain.enums import LogComponent

log = get_logger(LogComponent.USECASE_JOBS)


class EnqueueImportUseCase:
    def __init__(self, jobs: JobRepository) -> None:
        self._jobs = jobs

    async def execute(self, job_id: str, fingerprint: str, request: ImportRequest) -> JobRecord:
        job, created = await self._jobs.create_or_get(job_id, fingerprint, request)
        if created:
            log.info(
                "import queued",
                job_id=job.id,
                app=request.app,
                mode=request.transfer_mode,
                source=request.source_path,
            )
        return job
