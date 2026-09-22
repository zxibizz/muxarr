"""Operation history contract.

The records here are what the API serialises; they deliberately mirror the
stored columns rather than the ORM class, so the API never holds a live
SQLAlchemy instance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.journal import LogEntry, RejectedTrack, TrackDetail

MAX_PAGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class OperationRecord:
    id: int
    created_at: str
    app: str
    title: str
    move_status: str
    reason: str
    source_path: str
    destination_path: str
    media_file: str | None
    transfer_mode: str
    season: int | None
    episodes: list[int]
    added_tracks: list[TrackDetail]
    rejected_tracks: list[RejectedTrack]
    log: list[LogEntry]
    duration_ms: int
    source_bytes: int | None
    output_bytes: int | None
    dry_run: bool

    @property
    def muxed(self) -> bool:
        return self.move_status != "DeferMove"


@dataclass(frozen=True, slots=True)
class Stats:
    total: int
    muxed: int
    deferred: int
    tracks_added: int
    last_24h: int


@dataclass(frozen=True, slots=True)
class Page:
    items: list[OperationRecord]
    total: int
    limit: int
    offset: int


class HistoryRepository(Protocol):
    async def record(
        self,
        *,
        app: str,
        title: str,
        move_status: str,
        reason: str,
        source_path: str,
        destination_path: str,
        media_file: str | None = None,
        transfer_mode: str = "",
        season: int | None = None,
        episodes: Sequence[int] = (),
        added_tracks: Sequence[TrackDetail] = (),
        rejected_tracks: Sequence[RejectedTrack] = (),
        log: Sequence[LogEntry] = (),
        duration_ms: int = 0,
        source_bytes: int | None = None,
        output_bytes: int | None = None,
        dry_run: bool = False,
    ) -> int: ...

    async def get(self, operation_id: int) -> OperationRecord | None: ...

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        app: str | None = None,
        query: str | None = None,
    ) -> Page: ...

    async def stats(self) -> Stats: ...

    async def prune(self, keep_last: int) -> int:
        """Drop all but the ``keep_last`` newest operations, returning how many went."""
        ...

    async def clear(self) -> int: ...
