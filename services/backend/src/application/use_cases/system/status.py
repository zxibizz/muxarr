"""Daemon self-report.

The two processes only meet at the ``jobs`` table, so "is anything going to run
my import?" is not answerable from the API alone. A stale heartbeat next to a
growing ``pending`` count is the shape of a worker that has died.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.interfaces.jobs import JobRepository, WorkerStateRepository
from src.domain.health import HealthIssue
from src.settings.config import Settings


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
    # Most severe first.
    health: list[HealthIssue]


_SEVERITY = {"error": 0, "warning": 1, "notice": 2}


class GetSystemStatusUseCase:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        worker_state: WorkerStateRepository,
        stale_after_seconds: float,
        settings: Settings,
    ) -> None:
        self._jobs = jobs
        self._worker_state = worker_state
        self._stale_after = stale_after_seconds
        self._settings = settings

    async def worker_status(self) -> WorkerStatus:
        """Liveness alone, for callers that must not pay for the queue count."""
        last_seen = await self._worker_state.last_seen()
        return WorkerStatus(
            alive=is_fresh(last_seen, self._stale_after),
            last_seen_at=last_seen,
            stale_after_seconds=self._stale_after,
            max_concurrent_muxes=self._settings.max_concurrent_muxes,
        )

    async def execute(self) -> SystemStatus:
        counts = await self._jobs.counts_by_state()
        worker = await self.worker_status()
        # The worker's last report stands even when it is offline: it may say why.
        issues = [*self._own_checks(worker), *await self._worker_state.issues()]
        return SystemStatus(
            worker=worker,
            queue=QueueStatus(
                pending=counts["pending"],
                running=counts["running"],
                succeeded=counts["succeeded"],
                failed=counts["failed"],
            ),
            health=sorted(issues, key=lambda issue: _SEVERITY[issue.level]),
        )

    def _own_checks(self, worker: WorkerStatus) -> list[HealthIssue]:
        settings = self._settings
        issues: list[HealthIssue] = []
        if not worker.alive:
            since = f"since {worker.last_seen_at}" if worker.last_seen_at else "yet"
            issues.append(
                HealthIssue(
                    "error",
                    "worker_offline",
                    f"The worker has not checked in {since}: imports queue with nothing to "
                    "run them, and each one fails when its shim gives up.",
                )
            )
        if settings.container_mode != "all" and settings.db_url.startswith("sqlite"):
            issues.append(
                HealthIssue(
                    "warning",
                    "sqlite_split",
                    f"MUXARR_MODE={settings.container_mode} on SQLite only works while the web "
                    "and worker containers share one /config on one host. Use Postgres to run "
                    "them apart.",
                )
            )
        if settings.auth_method == "external":
            issues.append(
                HealthIssue(
                    "warning",
                    "login_off",
                    "The login is off (MUXARR_AUTH_METHOD=external): anything that reaches "
                    "this port without going through your proxy gets the UI and the API.",
                )
            )
        elif (
            settings.auth_required == "disabled_for_local_addresses"
            and not settings.trusted_proxies
        ):
            issues.append(
                HealthIssue(
                    "notice",
                    "proxies_untrusted",
                    "Local addresses skip the login and no reverse proxy is trusted. Behind "
                    "one, set MUXARR_TRUSTED_PROXIES, or every request counts as local.",
                )
            )
        return issues


def is_fresh(last_seen: str | None, stale_after: float) -> bool:
    if last_seen is None:
        return False
    try:
        seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(UTC) - seen).total_seconds() <= stale_after
