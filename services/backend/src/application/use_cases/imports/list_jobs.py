"""List recent jobs for the UI.

The history only holds imports that reached a decision. A job that broke the
daemon never gets there, so this is the only way to see what it was doing.
"""

from __future__ import annotations

from src.application.interfaces.jobs import JobPage, JobRepository
from src.domain.enums import JobState


class ListJobsUseCase:
    def __init__(self, jobs: JobRepository) -> None:
        self._jobs = jobs

    async def execute(
        self, *, state: JobState | None = None, limit: int = 20, offset: int = 0
    ) -> JobPage:
        return await self._jobs.list(state=state, limit=limit, offset=offset)
