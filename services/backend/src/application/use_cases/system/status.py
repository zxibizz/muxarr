"""Daemon self-report.

The two processes only meet at the ``jobs`` table, so "is anything going to run
my import?" is not answerable from the API alone. A stale heartbeat next to a
growing ``pending`` count is the shape of a worker that has died.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.interfaces.jobs import JobRepository, WorkerStateRepository


@dataclass(frozen=True, slots=True)
class WorkerStatus:
    alive: bool
    last_seen_at: str | None
    stale_after_seconds: float
    max_concurrent_muxes: int


@dataclass(frozen=True, slots=True)
class QueueStatus:
    pending: int
    running: int
    succeeded: int
    failed: int


@dataclass(frozen=True, slots=True)
class SystemStatus:
    worker: WorkerStatus
    queue: QueueStatus


class GetSystemStatusUseCase:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        worker_state: WorkerStateRepository,
        stale_after_seconds: float,
        max_concurrent_muxes: int,
    ) -> None:
        self._jobs = jobs
        self._worker_state = worker_state
        self._stale_after = stale_after_seconds
        self._max_concurrent = max_concurrent_muxes

    async def worker_status(self) -> WorkerStatus:
        """Liveness alone, for callers that must not pay for the queue count."""
        last_seen = await self._worker_state.last_seen()
        return WorkerStatus(
            alive=is_fresh(last_seen, self._stale_after),
            last_seen_at=last_seen,
            stale_after_seconds=self._stale_after,
            max_concurrent_muxes=self._max_concurrent,
        )

    async def execute(self) -> SystemStatus:
        counts = await self._jobs.counts_by_state()
        return SystemStatus(
            worker=await self.worker_status(),
            queue=QueueStatus(
                pending=counts["pending"],
                running=counts["running"],
                succeeded=counts["succeeded"],
                failed=counts["failed"],
            ),
        )


def is_fresh(last_seen: str | None, stale_after: float) -> bool:
    if last_seen is None:
        return False
    try:
        seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(UTC) - seen).total_seconds() <= stale_after
