"""System status wire model."""

from __future__ import annotations

from src.schemas.base import WireModel


class WorkerStatusModel(WireModel):
    alive: bool
    # Null until the worker has run once.
    last_seen_at: str | None
    stale_after_seconds: float
    max_concurrent_muxes: int


class QueueStatusModel(WireModel):
    pending: int
    running: int
    # Finished jobs are pruned on their TTL, so these cover a recent window.
    succeeded: int
    failed: int


class SystemStatus(WireModel):
    version: str
    worker: WorkerStatusModel
    queue: QueueStatusModel
