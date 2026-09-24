"""Health wire model."""

from __future__ import annotations

from typing import Literal

from src.schemas.base import WireModel


class Health(WireModel):
    status: Literal["ok"] = "ok"
    version: str
    read_roots: list[str]
    # Null until the worker has run once. Stale means queued imports are piling
    # up: nothing but the worker ever muxes.
    worker_seen_at: str | None = None
    worker_alive: bool = False
