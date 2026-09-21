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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from src.application.use_cases.imports.dto import ImportOutcome, ImportRequest
from src.domain.enums import TERMINAL_JOB_STATES, JobState
from src.domain.errors import MuxarrError


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

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_JOB_STATES


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
