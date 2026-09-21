"""In-memory job registry for asynchronous imports.

The *arr shims cannot hold one HTTP request open for the length of a remux: any
proxy idle timeout or network blip kills it, and the shim then has no way to tell
"the mux failed" from "I lost the reply to a mux that is still running". So the
work is registered here under a client-supplied id, and the shim long-polls for
the outcome with short, individually retryable requests.

State lives in the process only. A restart loses every job, which the shim reads
as :data:`UNKNOWN` and turns into a failed import -- deliberately, because the
source file may have been half-moved by the mux that died with it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from muxarr.errors import MuxarrError
from muxarr.pipeline import ImportOutcome

log = logging.getLogger(__name__)

JobState = Literal["pending", "running", "succeeded", "failed"]

TERMINAL_STATES: frozenset[str] = frozenset({"succeeded", "failed"})

DEFAULT_TTL_SECONDS = 60 * 60.0
DEFAULT_MAX_JOBS = 1000


class JobConflictError(MuxarrError):
    """A job id was reused for a different import."""


@dataclass(slots=True)
class Job:
    id: str
    fingerprint: str
    state: JobState = "pending"
    outcome: ImportOutcome | None = None
    error: str | None = None
    history_id: int | None = None
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    # Set on every transition so waiters wake the instant a mux finishes rather
    # than on their next poll.
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    # Without a strong reference the event loop may garbage-collect a running
    # task mid-mux; the job would then hang in "running" forever.
    task: asyncio.Task[None] | None = None

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_STATES


def fingerprint(payload: object) -> str:
    """Stable digest of an import request, used to detect id reuse."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class JobStore:
    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_jobs: int = DEFAULT_MAX_JOBS,
    ) -> None:
        self._jobs: dict[str, Job] = {}
        self._ttl = ttl_seconds
        self._max_jobs = max_jobs

    def create_or_get(self, job_id: str, request_fingerprint: str) -> tuple[Job, bool]:
        """Return the job for ``job_id``, creating it if new.

        The second element is True only when this call created the job, so a
        retried submission re-attaches to the running mux instead of starting a
        second one.
        """
        self._evict()
        existing = self._jobs.get(job_id)
        if existing is not None:
            if existing.fingerprint != request_fingerprint:
                raise JobConflictError(
                    f"job {job_id} already exists for a different import"
                )
            return existing, False

        job = Job(id=job_id, fingerprint=request_fingerprint)
        self._jobs[job_id] = job
        return job, True

    def get(self, job_id: str) -> Job | None:
        self._evict()
        return self._jobs.get(job_id)

    def start(self, job_id: str) -> None:
        self._transition(job_id, "running")

    def succeed(self, job_id: str, outcome: ImportOutcome, history_id: int | None) -> None:
        self._transition(job_id, "succeeded", outcome=outcome, history_id=history_id)

    def fail(self, job_id: str, error: str) -> None:
        self._transition(job_id, "failed", error=error)

    def _transition(
        self,
        job_id: str,
        state: JobState,
        *,
        outcome: ImportOutcome | None = None,
        error: str | None = None,
        history_id: int | None = None,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            log.warning("transition to %s for unknown job %s", state, job_id)
            return
        job.state = state
        job.updated_at = time.monotonic()
        if outcome is not None:
            job.outcome = outcome
        if error is not None:
            job.error = error
        if history_id is not None:
            job.history_id = history_id
        job.changed.set()

    async def wait(self, job_id: str, timeout: float) -> Job | None:
        """Block until the job reaches a terminal state or ``timeout`` elapses.

        Returns the job in whatever state it is in when the wait ends, or None if
        the id is unknown.
        """
        job = self.get(job_id)
        if job is None or job.done or timeout <= 0:
            return job

        deadline = time.monotonic() + timeout
        while not job.done:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            job.changed.clear()
            # Re-check after clearing: the transition may have landed in between.
            if job.done:
                break
            try:
                await asyncio.wait_for(job.changed.wait(), timeout=remaining)
            except TimeoutError:
                break
        return job

    def _evict(self) -> None:
        """Drop finished jobs past their TTL, and the oldest if over capacity.

        Evicting a job the shim has not read yet makes it fail the import, so the
        TTL is generous compared with the poll interval.
        """
        now = time.monotonic()
        for job_id, job in list(self._jobs.items()):
            if job.done and now - job.updated_at > self._ttl:
                del self._jobs[job_id]

        overflow = len(self._jobs) - self._max_jobs
        if overflow <= 0:
            return
        finished = sorted(
            (job for job in self._jobs.values() if job.done),
            key=lambda job: job.updated_at,
        )
        for job in finished[:overflow]:
            del self._jobs[job.id]
