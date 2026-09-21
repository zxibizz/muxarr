"""Asynchronous import job contract.

The *arr shims cannot hold one HTTP request open for the length of a remux: any
proxy idle timeout or network blip kills it, and the shim then has no way to tell
"the mux failed" from "I lost the reply to a mux that is still running". So the
work is registered under a client-supplied id and the shim long-polls for the
outcome with short, individually retryable requests.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal, Protocol

from src.application.use_cases.imports.dto import ImportOutcome
from src.domain.errors import MuxarrError

JobState = Literal["pending", "running", "succeeded", "failed"]

TERMINAL_STATES: frozenset[str] = frozenset({"succeeded", "failed"})


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


class JobStore(Protocol):
    def create_or_get(self, job_id: str, request_fingerprint: str) -> tuple[Job, bool]: ...

    def get(self, job_id: str) -> Job | None: ...

    def start(self, job_id: str) -> None: ...

    def succeed(self, job_id: str, outcome: ImportOutcome, history_id: int | None) -> None: ...

    def fail(self, job_id: str, error: str) -> None: ...

    async def wait(self, job_id: str, timeout: float) -> Job | None: ...
