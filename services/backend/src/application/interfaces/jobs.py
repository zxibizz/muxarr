"""Asynchronous import job contract.

The *arr shims cannot hold one HTTP request open for the length of a remux: any
proxy idle timeout or network blip kills it, and the shim then has no way to tell
"the mux failed" from "I lost the reply to a mux that is still running". So the
work is queued under a client-supplied id and the shim long-polls for the
outcome with short, individually retryable requests.

Jobs are persisted because the API and the worker are separate processes. A row
left in ``running`` by a worker that died is reconciled to ``failed`` when the
worker next starts -- the shim then fails the import, which is the safe answer
when a mux may have half-written a file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.domain.enums import TERMINAL_JOB_STATES, JobState
from src.domain.errors import MuxarrError
from src.domain.health import HealthIssue
from src.domain.journal import LogEntry

MAX_JOB_PAGE_SIZE = 200


class JobConflictError(MuxarrError):
    """A job id was reused for a different import."""


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    fingerprint: str
    state: JobState
    request: ImportRequest
    outcome: ImportOutcome | None = None
    error: str | None = None
    history_id: int | None = None
    created_at: str = ""
    updated_at: str = ""
    log: list[LogEntry] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_JOB_STATES


@dataclass(frozen=True, slots=True)
class JobPage:
    items: list[JobRecord]
    total: int
    limit: int
    offset: int


class JobRepository(Protocol):
    async def create_or_get(
        self, job_id: str, fingerprint: str, request: ImportRequest
    ) -> tuple[JobRecord, bool]:
        """Return the job for ``job_id``, creating it if new.

        The second element is True only when this call created it, so a retried
        submission re-attaches instead of queueing a second mux.
        """
        ...

    async def get(self, job_id: str) -> JobRecord | None: ...

    async def list(
        self, *, state: JobState | None = None, limit: int = 20, offset: int = 0
    ) -> JobPage:
        """Recent jobs, newest first.

        This is how a job that never reached the history is inspected: a failed
        one writes no operation row, so its log is the only account of it.
        """
        ...

    async def save_log(self, job_id: str, entries: Sequence[LogEntry]) -> None:
        """Replace the job's captured log.

        Called while the job runs so the UI can follow it, which is why it takes
        the whole buffer rather than a delta -- the writer already holds it, and
        a blob rewrite keeps the row consistent without a second table.
        """
        ...

    async def claim_next(self) -> JobRecord | None:
        """Atomically move the oldest pending job to ``running``."""
        ...

    async def succeed(
        self, job_id: str, outcome: ImportOutcome, history_id: int | None
    ) -> None: ...

    async def fail(self, job_id: str, error: str) -> None: ...

    async def fail_running(self, error: str) -> int:
        """Fail every job left ``running``, returning how many.

        Pending jobs are untouched: nothing has started them, so the worker
        doing the reconciling is about to pick them up.
        """
        ...

    async def prune(self, older_than_seconds: float) -> int:
        """Drop finished jobs past their TTL, returning how many."""
        ...

    async def counts_by_state(self) -> Mapping[JobState, int]:
        """How many jobs sit in each state, with every state present.

        Finished jobs are pruned on their TTL, so the terminal counts describe a
        recent window rather than all time.
        """
        ...


class WorkerStateRepository(Protocol):
    async def heartbeat(self) -> None: ...

    async def last_seen(self) -> str | None: ...

    async def report(self, issues: Sequence[HealthIssue]) -> None:
        """Replace the worker's health checks; only it can see its mounts and tools."""
        ...

    async def issues(self) -> list[HealthIssue]: ...
