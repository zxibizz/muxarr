"""Long-poll a job to completion.

The worker runs in another process, so there is no in-process event to wait on;
the job row is re-read until it settles. The interval is short enough that the
shim learns about completion well within a second of the mux finishing.
"""

from __future__ import annotations

import asyncio
import time

from src.application.interfaces.jobs import JobRecord, JobRepository

POLL_INTERVAL = 0.25


class AwaitJobUseCase:
    def __init__(self, jobs: JobRepository) -> None:
        self._jobs = jobs

    async def execute(self, job_id: str, timeout: float) -> JobRecord | None:
        """Return the job once terminal, or as it stands when ``timeout`` elapses.

        An unknown id returns immediately: holding the request open would only
        delay the shim's failure, since nothing can create that job now.
        """
        job = await self._jobs.get(job_id)
        if job is None or job.done or timeout <= 0:
            return job

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return job
            await asyncio.sleep(min(POLL_INTERVAL, remaining))
            job = await self._jobs.get(job_id)
            if job is None or job.done:
                return job
